"""``bk worker``: the scheduler process (spec 5 stage 1, PLAN 2: APScheduler + Postgres
advisory locks, no Redis).

One APScheduler interval job ticks every minute and runs every active/testing source
whose own cron schedule is due (see worker/runner.py). Because the schedule is read
from the database on each tick, sources added or edited in the admin screen are
picked up without a restart. Sources run one after another on one shared HTTP
client, so per-host delays and robots.txt caching hold across sources.

Each tick (and start-up) first closes source runs left ``running`` by a worker that
stopped: older than ``BK_STALE_RUN_MINUTES`` (default 120) and with no worker
holding the source's lock, they are marked failed with "worker stopped".

A second job runs once a day (and once at start-up) to move catalogue statuses on
as deadlines pass (open -> closing_soon -> expired), under its own advisory lock.

Pending profile backfills (worker/backfills.py: new or edited profiles, mute
changes) run on every tick after the sources and their alerts, at most
``BK_BACKFILL_PER_TICK`` profiles a tick, debounced, backed off on failure and under
a lock per profile, so a backlog never delays collection. They are never run in an
HTTP request (spec 5 cost guard).

Delivery (delivery/jobs.py): the weekly digest runs on Mondays at
``BK_DIGEST_HOUR`` Africa/Kigali (and at start-up, where it does nothing unless it
is Monday after that hour and a user's digest has not gone yet); urgent alerts run
after the sources when a source run succeeded (after ingest and scoring), and
again after the backfills when one ran (a new profile can find older items). Both take their own advisory lock and are idempotent per user per day.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session, sessionmaker

from blackkite.collectors.http import DbHttpCache, FetchClient, make_fetch_client
from blackkite.config import Settings
from blackkite.delivery.jobs import alerts_job, weekly_digest_job
from blackkite.delivery.mail import MailTransport, make_transport
from blackkite.worker.backfills import run_pending_backfills
from blackkite.worker.runner import (
    fail_stale_runs,
    refresh_statuses_locked,
    run_due_sources,
)

log = logging.getLogger("blackkite.worker")

TICK_SECONDS = 60
# 22:05 UTC = 00:05 Africa/Kigali, just after the Kigali day turns.
REFRESH_STATUSES_CRON = "5 22 * * *"


def close_stale_runs(sessions: sessionmaker[Session], settings: Settings) -> int:
    return fail_stale_runs(sessions, timedelta(minutes=settings.stale_run_minutes))


KIGALI_TZ = ZoneInfo("Africa/Kigali")


def tick(
    sessions: sessionmaker[Session],
    client: FetchClient,
    settings: Settings,
    transport: MailTransport | None = None,
) -> None:
    try:
        close_stale_runs(sessions, settings)
    except Exception:  # never let housekeeping stop the sources
        log.exception("could not close stale source runs")
    outcomes = run_due_sources(
        sessions,
        client=client,
        default_schedule=settings.default_source_schedule,
        brave_api_key=settings.brave_api_key,
    )
    for o in outcomes:
        log.info(
            "source %s: %s (found %d, new %d, failed %d)%s",
            o.name,
            o.status,
            o.items_found,
            o.items_new,
            o.items_failed,
            f" error: {o.error}" if o.error else "",
        )
    transport = transport or make_transport(settings)
    if any(o.status == "succeeded" for o in outcomes):
        alerts(sessions, settings, transport)
    # Last, so a backlog of profile backfills never delays collection or alerts.
    if backfills(sessions, settings):
        alerts(sessions, settings, transport)


def backfills(sessions: sessionmaker[Session], settings: Settings) -> int:
    """Pending profile backfills. Never lets a failure stop the tick."""
    try:
        done = run_pending_backfills(
            sessions,
            per_tick=settings.backfill_per_tick,
            max_attempts=settings.backfill_max_attempts,
        )
    except Exception:
        log.exception("profile backfills failed")
        return 0
    if done:
        log.info("backfills: %d profile(s) scored", len(done))
    return len(done)


def alerts(
    sessions: sessionmaker[Session], settings: Settings, transport: MailTransport
) -> None:
    """Urgent alerts after an ingest cycle. Never lets a failure stop the tick."""
    try:
        sent = alerts_job(sessions, settings, transport)
    except Exception:
        log.exception("urgent alerts failed")
        return
    if sent is None:
        log.info("alerts: another worker holds the lock; skipped")
    elif sent:
        log.info("alerts: %d item(s) sent", sent)


def digest_job(
    sessions: sessionmaker[Session], settings: Settings, transport: MailTransport
) -> None:
    counts = weekly_digest_job(sessions, settings, transport)
    if counts is None:
        log.info("weekly digest: another worker holds the lock; skipped")
    elif counts:
        log.info("weekly digest: %s", dict(counts))


def refresh_job(sessions: sessionmaker[Session]) -> None:
    changed = refresh_statuses_locked(sessions)
    if changed is None:
        log.info("status refresh: another worker holds the lock; skipped")
    else:
        log.info("status refresh: %d opportunities changed status", changed)


def build_scheduler(
    sessions: sessionmaker[Session],
    settings: Settings,
    client: FetchClient | None = None,
    transport: MailTransport | None = None,
) -> BlockingScheduler:
    client = client or make_fetch_client(settings, cache=DbHttpCache(sessions))
    transport = transport or make_transport(settings)
    sched = BlockingScheduler(timezone=UTC)
    sched.add_job(
        tick,
        IntervalTrigger(seconds=TICK_SECONDS, timezone=UTC),
        args=(sessions, client, settings, transport),
        id="run-due-sources",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(UTC),
    )
    sched.add_job(
        refresh_job,
        CronTrigger.from_crontab(REFRESH_STATUSES_CRON, timezone=UTC),
        args=(sessions,),
        id="refresh-statuses",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(UTC),
    )
    sched.add_job(
        digest_job,
        CronTrigger(
            day_of_week="mon", hour=settings.digest_hour, minute=0, timezone=KIGALI_TZ
        ),
        args=(sessions, settings, transport),
        id="weekly-digest",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=6 * 3600,
        next_run_time=datetime.now(UTC),  # catch up after a restart on Monday
    )
    return sched


def main(settings: Settings, sessions: sessionmaker[Session]) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    if not settings.bot_contact_url:
        log.warning("BK_BOT_CONTACT_URL is not set; the User-Agent has no contact URL")
    close_stale_runs(sessions, settings)  # runs left by a worker that stopped
    sched = build_scheduler(sessions, settings)
    log.info("worker started; checking sources every %ds", TICK_SECONDS)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("worker stopped")
