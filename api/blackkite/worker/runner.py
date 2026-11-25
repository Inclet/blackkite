"""Collect stage (spec 5 stage 1): run sources, record source_run rows.

``run_source`` writes a ``source_run`` row (running -> succeeded / failed), calls the
collector, hands the items to ``blackkite.pipeline.ingest.ingest_items``. The
ingest writes and the run's success are committed together; on any failure the
ingest work is rolled back and the run is marked failed with the error text.

The pipeline's fetcher (detail pages and PDFs, enrich stage) is the run's own
``FetchClient`` wrapped in ``ClientFetcher`` with the source's rate limit, so
enrichment gets the same URL guard, robots.txt, per-host delay, User-Agent, size
cap and cache as collection. ``make_deps(fetcher) -> PipelineDeps`` builds the
rest (model clients); it defaults to ``ingest.default_deps``.

``run_due_sources`` runs every active/testing source whose schedule says a run is
due. Each source is isolated: one failing (even with an unexpected exception)
never stops the others. A Postgres advisory lock per source makes sure two
workers never run the same source at once.

Schedules are 5-field cron in UTC (``source.schedule``); NULL means the default
(``BK_DEFAULT_SOURCE_SCHEDULE``, 04:00 UTC = 06:00 Africa/Kigali). A source is due
when the first fire time after its last run started (or, if it never ran, after it
was created) has passed.
"""

from __future__ import annotations

import logging
import uuid
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

from blackkite.collectors.base import CollectorError
from blackkite.collectors.http import ClientFetcher, FetchClient
from blackkite.collectors.registry import build_collector
from blackkite.db.models import Source, SourceRun
from blackkite.pipeline import ingest
from blackkite.pipeline.enrich import Fetcher
from blackkite.sources.service import SCHEDULED_STATUSES, parse_schedule

log = logging.getLogger("blackkite.worker")

ERROR_MAX_CHARS = 2000
# First key of the two-int advisory lock: "BK". Second: crc32 of the source id.
LOCK_NAMESPACE = 0x424B
# Periodic jobs that are not sources: their own namespace ("BJ"), one key per job.
JOB_LOCK_NAMESPACE = 0x424A
REFRESH_STATUSES_KEY = 1

DepsFactory = Callable[[Fetcher], ingest.PipelineDeps]


def _now() -> datetime:
    return datetime.now(UTC)


def _error_text(e: BaseException) -> str:
    text = str(e) if isinstance(e, CollectorError) else f"{type(e).__name__}: {e}"
    text = text or type(e).__name__
    if len(text) > ERROR_MAX_CHARS:
        text = text[: ERROR_MAX_CHARS - 15] + " ...[truncated]"
    return text


def run_source(
    session: Session,
    source: Source,
    *,
    client: FetchClient,
    brave_api_key: SecretStr | None = None,
    make_deps: DepsFactory | None = None,
    now=_now,
) -> SourceRun:
    run = SourceRun(source_id=source.id, status="running", started_at=now())
    session.add(run)
    session.commit()
    run_id = run.id
    try:
        collector = build_collector(
            source.collector_type, client, brave_api_key=brave_api_key
        )
        items = collector.fetch(source)
        fetcher = ClientFetcher(client, delay=source.rate_limit)
        deps = (make_deps or ingest.default_deps)(fetcher)
        result = ingest.ingest_items(session, source, items, deps=deps, now=now())
        run.status = "succeeded"
        run.items_found = result.items_found
        run.items_new = result.items_new
        run.items_failed = result.items_failed
        run.finished_at = now()
        session.commit()
    except Exception as e:  # one source's failure is recorded, never propagated
        if isinstance(e, CollectorError):
            log.warning("source %s failed: %s", source.name, e)
        else:
            log.exception("source %s crashed", source.name)
        session.rollback()
        run = session.get(SourceRun, run_id)
        assert run is not None
        run.status = "failed"
        run.error = _error_text(e)
        run.finished_at = now()
        session.commit()
    return run


# --- locking ------------------------------------------------------------------------


def lock_key(source_id: uuid.UUID) -> int:
    return zlib.crc32(source_id.bytes) - (1 << 31)  # signed int4


@contextmanager
def advisory_lock(engine: sa.Engine, namespace: int, key: int) -> Iterator[bool]:
    """Session-level advisory lock on its own connection (independent of the work's
    transactions). Yields False if another worker holds it."""
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        got = bool(conn.scalar(sa.select(sa.func.pg_try_advisory_lock(namespace, key))))
        try:
            yield got
        finally:
            if got:
                conn.scalar(sa.select(sa.func.pg_advisory_unlock(namespace, key)))


def source_lock(engine: sa.Engine, source_id: uuid.UUID):
    return advisory_lock(engine, LOCK_NAMESPACE, lock_key(source_id))


# --- runs left behind by a stopped worker ------------------------------------------------

STALE_RUN_ERROR = "worker stopped"


def fail_stale_runs(
    sessions: sessionmaker[Session], max_age: timedelta, now=_now
) -> int:
    """Mark ``running`` source_run rows older than ``max_age`` as failed with
    "worker stopped". A run whose source lock is held by a live worker is left
    alone, however old. Returns how many rows were closed."""
    closed = 0
    with sessions() as s:
        cutoff = now() - max_age
        rows = s.execute(
            sa.select(SourceRun.id, SourceRun.source_id).where(
                SourceRun.status == "running", SourceRun.started_at < cutoff
            )
        ).all()
        for run_id, source_id in rows:
            with source_lock(s.get_bind(), source_id) as got:
                if not got:
                    continue  # still being run by a live worker
                n = s.execute(
                    sa.update(SourceRun)
                    .where(SourceRun.id == run_id, SourceRun.status == "running")
                    .values(status="failed", error=STALE_RUN_ERROR, finished_at=now())
                ).rowcount
                s.commit()
                closed += n
    if closed:
        log.warning("marked %d stale source run(s) failed: %s", closed, STALE_RUN_ERROR)
    return closed


# --- daily status refresh -------------------------------------------------------------


def refresh_statuses_locked(sessions: sessionmaker[Session], now=_now) -> int | None:
    """Move open/closing_soon items on as deadlines pass (ingest.refresh_statuses),
    under its own advisory lock. Returns how many changed, or None if another
    worker holds the lock."""
    with (
        sessions() as s,
        advisory_lock(s.get_bind(), JOB_LOCK_NAMESPACE, REFRESH_STATUSES_KEY) as got,
    ):
        if not got:
            return None
        changed = ingest.refresh_statuses(s, now())
        s.commit()
        return changed


# --- schedule -----------------------------------------------------------------------


def last_started(session: Session, source_id: uuid.UUID) -> datetime | None:
    return session.scalar(
        sa.select(sa.func.max(SourceRun.started_at)).where(
            SourceRun.source_id == source_id
        )
    )


def is_due(
    source: Source, last_start: datetime | None, now: datetime, default_schedule: str
) -> bool:
    expr = source.schedule or default_schedule
    try:
        trigger = parse_schedule(expr)
    except ValueError:
        log.error("source %s has an invalid schedule %r; not run", source.name, expr)
        return False
    reference = (last_start or source.created_at) + timedelta(seconds=1)
    nxt = trigger.get_next_fire_time(None, reference)
    return nxt is not None and nxt <= now


@dataclass(frozen=True)
class RunOutcome:
    source_id: uuid.UUID
    name: str
    status: str  # succeeded | failed | skipped_locked | skipped_not_due
    items_found: int = 0
    items_new: int = 0
    error: str | None = None
    items_failed: int = 0


def run_source_locked(
    sessions: sessionmaker[Session],
    source_id: uuid.UUID,
    *,
    client: FetchClient,
    brave_api_key: SecretStr | None = None,
    default_schedule: str | None = None,
    make_deps: DepsFactory | None = None,
    now=_now,
) -> RunOutcome:
    """Run one source under its advisory lock. With ``default_schedule`` set, the
    source is re-checked for due-ness inside the lock (another worker may have just
    run it); without it the run is forced (CLI ``bk run-source``)."""
    with sessions() as s:
        source = s.get(Source, source_id)
        if source is None:
            raise LookupError(source_id)
        with source_lock(s.get_bind(), source_id) as got:
            if not got:
                return RunOutcome(source_id, source.name, "skipped_locked")
            if default_schedule is not None:
                s.expire_all()
                source = s.get(Source, source_id)
                if source is None or source.status not in SCHEDULED_STATUSES:
                    return RunOutcome(source_id, "?", "skipped_not_due")
                if not is_due(
                    source, last_started(s, source_id), now(), default_schedule
                ):
                    return RunOutcome(source_id, source.name, "skipped_not_due")
            run = run_source(
                s,
                source,
                client=client,
                brave_api_key=brave_api_key,
                make_deps=make_deps,
                now=now,
            )
            return RunOutcome(
                source_id,
                source.name,
                run.status,
                run.items_found,
                run.items_new,
                run.error,
                run.items_failed,
            )


def due_source_ids(
    session: Session, now: datetime, default_schedule: str
) -> list[uuid.UUID]:
    sources = session.scalars(
        sa.select(Source)
        .where(Source.status.in_(SCHEDULED_STATUSES))
        .order_by(Source.name)
    ).all()
    starts = dict(
        session.execute(
            sa.select(SourceRun.source_id, sa.func.max(SourceRun.started_at)).group_by(
                SourceRun.source_id
            )
        ).all()
    )
    return [s.id for s in sources if is_due(s, starts.get(s.id), now, default_schedule)]


def run_due_sources(
    sessions: sessionmaker[Session],
    *,
    client: FetchClient,
    default_schedule: str,
    brave_api_key: SecretStr | None = None,
    make_deps: DepsFactory | None = None,
    now=_now,
) -> list[RunOutcome]:
    with sessions() as s:
        ids = due_source_ids(s, now(), default_schedule)
    outcomes: list[RunOutcome] = []
    for sid in ids:
        try:
            outcomes.append(
                run_source_locked(
                    sessions,
                    sid,
                    client=client,
                    brave_api_key=brave_api_key,
                    default_schedule=default_schedule,
                    make_deps=make_deps,
                    now=now,
                )
            )
        except Exception as e:  # e.g. the database blipped; the next source still runs
            log.exception("could not run source %s", sid)
            outcomes.append(RunOutcome(sid, "?", "failed", error=_error_text(e)))
    return outcomes
