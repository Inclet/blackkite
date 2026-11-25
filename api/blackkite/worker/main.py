"""``bk worker``: the scheduler process (spec 5 stage 1, PLAN 2: APScheduler + Postgres
advisory locks, no Redis).

One APScheduler interval job ticks every minute and runs every active/testing source
whose own cron schedule is due (see worker/runner.py). Because the schedule is read
from the database on each tick, sources added or edited in the admin screen are
picked up without a restart. Sources run one after another on one shared HTTP
client, so per-host delays and robots.txt caching hold across sources.

A second job runs once a day (and once at start-up) to move catalogue statuses on
as deadlines pass (open -> closing_soon -> expired), under its own advisory lock.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session, sessionmaker

from blackkite.collectors.http import DbHttpCache, FetchClient, make_fetch_client
from blackkite.config import Settings
from blackkite.worker.runner import refresh_statuses_locked, run_due_sources

log = logging.getLogger("blackkite.worker")

TICK_SECONDS = 60
# 22:05 UTC = 00:05 Africa/Kigali, just after the Kigali day turns.
REFRESH_STATUSES_CRON = "5 22 * * *"


def tick(
    sessions: sessionmaker[Session], client: FetchClient, settings: Settings
) -> None:
    outcomes = run_due_sources(
        sessions,
        client=client,
        default_schedule=settings.default_source_schedule,
        brave_api_key=settings.brave_api_key,
    )
    for o in outcomes:
        log.info(
            "source %s: %s (found %d, new %d)%s",
            o.name,
            o.status,
            o.items_found,
            o.items_new,
            f" error: {o.error}" if o.error else "",
        )


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
) -> BlockingScheduler:
    client = client or make_fetch_client(settings, cache=DbHttpCache(sessions))
    sched = BlockingScheduler(timezone=UTC)
    sched.add_job(
        tick,
        IntervalTrigger(seconds=TICK_SECONDS, timezone=UTC),
        args=(sessions, client, settings),
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
    return sched


def main(settings: Settings, sessions: sessionmaker[Session]) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    if not settings.bot_contact_url:
        log.warning("BK_BOT_CONTACT_URL is not set; the User-Agent has no contact URL")
    sched = build_scheduler(sessions, settings)
    log.info("worker started; checking sources every %ds", TICK_SECONDS)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("worker stopped")
