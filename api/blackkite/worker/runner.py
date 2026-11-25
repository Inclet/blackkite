"""Collect stage (spec 5 stage 1): run sources, record source_run rows.

``run_source`` writes a ``source_run`` row (running -> succeeded / failed), calls the
collector, hands the items to ``blackkite.pipeline.ingest.ingest_items``. The
ingest writes and the run's success are committed together; on any failure the
ingest work is rolled back and the run is marked failed with the error text.

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
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

from blackkite.collectors.base import CollectorError
from blackkite.collectors.http import FetchClient
from blackkite.collectors.registry import build_collector
from blackkite.db.models import Source, SourceRun
from blackkite.pipeline import ingest
from blackkite.sources.service import SCHEDULED_STATUSES, parse_schedule

log = logging.getLogger("blackkite.worker")

ERROR_MAX_CHARS = 2000
# First key of the two-int advisory lock: "BK". Second: crc32 of the source id.
LOCK_NAMESPACE = 0x424B


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
        result = ingest.ingest_items(session, source, items)
        run.status = "succeeded"
        run.items_found = result.items_found
        run.items_new = result.items_new
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
def source_lock(engine: sa.Engine, source_id: uuid.UUID) -> Iterator[bool]:
    """Session-level advisory lock on its own connection (independent of the run's
    transactions). Yields False if another worker holds it."""
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        got = bool(
            conn.scalar(
                sa.select(
                    sa.func.pg_try_advisory_lock(LOCK_NAMESPACE, lock_key(source_id))
                )
            )
        )
        try:
            yield got
        finally:
            if got:
                conn.scalar(
                    sa.select(
                        sa.func.pg_advisory_unlock(LOCK_NAMESPACE, lock_key(source_id))
                    )
                )


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


def run_source_locked(
    sessions: sessionmaker[Session],
    source_id: uuid.UUID,
    *,
    client: FetchClient,
    brave_api_key: SecretStr | None = None,
    default_schedule: str | None = None,
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
                s, source, client=client, brave_api_key=brave_api_key, now=now
            )
            return RunOutcome(
                source_id,
                source.name,
                run.status,
                run.items_found,
                run.items_new,
                run.error,
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
                    now=now,
                )
            )
        except Exception as e:  # e.g. the database blipped; the next source still runs
            log.exception("could not run source %s", sid)
            outcomes.append(RunOutcome(sid, "?", "failed", error=_error_text(e)))
    return outcomes
