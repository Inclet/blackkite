"""Worker job: run pending profile backfills (scoring/backfill.py).

Every tick, profiles whose newest request is at least ``BACKFILL_DEBOUNCE`` old
are backfilled one at a time, each under a Postgres advisory lock per profile
(two workers never score the same profile at once). The request is cleared only
if no newer one arrived during the run; otherwise the profile runs again once
the newer request is old enough. An inactive profile's request is just cleared
(activation always asks again).

A failure never stops the other profiles. It leaves the request in place with
``backfill_attempts`` counted up and the next try pushed back by a growing delay
(``BACKOFF``: 1, 5, 15, 60 minutes, then hourly). After ``max_attempts`` failures
(``BK_BACKFILL_MAX_ATTEMPTS``, default 6) the request is dropped with a logged
error; a new request (a profile edit, a mute change) starts the count again.

At most ``per_tick`` profiles (``BK_BACKFILL_PER_TICK``, default 5) are scored per
call, oldest request first; the rest wait for the next tick. The worker runs this
after source collection and alerts (worker/main.py), so a backlog never delays
collection.
"""

from __future__ import annotations

import logging
import uuid
import zlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from blackkite.db.models import Profile
from blackkite.scoring.backfill import BACKFILL_DEBOUNCE
from blackkite.worker.runner import advisory_lock

log = logging.getLogger("blackkite.worker")

# Advisory lock namespace for profile backfills ("BP"); key: crc32 of the id.
PROFILE_LOCK_NAMESPACE = 0x4250

# Delay before retry n after a failure (n = 1, 2, ...); the last one repeats.
BACKOFF = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(minutes=60),
)
DEFAULT_PER_TICK = 5
DEFAULT_MAX_ATTEMPTS = 6


def backoff(attempts: int) -> timedelta:
    """Delay after the ``attempts``-th failure (1-based)."""
    return BACKOFF[min(max(attempts, 1), len(BACKOFF)) - 1]


def _now() -> datetime:
    return datetime.now(UTC)


def profile_lock_key(profile_id: uuid.UUID) -> int:
    return zlib.crc32(profile_id.bytes) - (1 << 31)  # signed int4


def due_backfills(session: Session, now: datetime) -> list[uuid.UUID]:
    return list(
        session.scalars(
            sa.select(Profile.id)
            .where(Profile.backfill_requested_at <= now - BACKFILL_DEBOUNCE)
            .order_by(Profile.backfill_requested_at, Profile.id)
        )
    )


def _clear(
    session: Session,
    profile_id: uuid.UUID,
    requested: datetime,
    to: datetime | None,
    attempts: int = 0,
) -> None:
    """Set the request to ``to`` unless a newer one arrived meanwhile (a newer
    request has reset the attempts itself). Not an edit: ``updated_at`` stays."""
    session.execute(
        sa.update(Profile)
        .where(Profile.id == profile_id, Profile.backfill_requested_at == requested)
        .values(
            backfill_requested_at=to,
            backfill_attempts=attempts,
            updated_at=Profile.updated_at,
        )
        .execution_options(synchronize_session=False)
    )


def _record_failure(
    session: Session,
    profile_id: uuid.UUID,
    requested: datetime,
    attempts: int,
    at: datetime,
    max_attempts: int,
) -> None:
    if attempts >= max_attempts:
        log.error(
            "backfill for profile %s failed %d times; given up until the next edit",
            profile_id,
            attempts,
        )
        _clear(session, profile_id, requested, None, attempts)
    else:
        # Due again when requested_at <= now - debounce, i.e. at + backoff.
        retry = at + backoff(attempts) - BACKFILL_DEBOUNCE
        log.warning(
            "backfill for profile %s: attempt %d failed; retry after %s",
            profile_id,
            attempts,
            retry + BACKFILL_DEBOUNCE,
        )
        _clear(session, profile_id, requested, retry, attempts)


def run_pending_backfills(
    sessions: sessionmaker[Session],
    now: Callable[[], datetime] = _now,
    deps=None,
    *,
    per_tick: int = DEFAULT_PER_TICK,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> list[uuid.UUID]:
    """Backfill up to ``per_tick`` due profiles. Returns the ids actually
    backfilled."""
    from blackkite.scoring import service

    at = now()
    with sessions() as s:
        due = due_backfills(s, at)
    done: list[uuid.UUID] = []
    if not due:
        return done
    deps = deps or service.default_deps()
    tried = 0
    for i, pid in enumerate(due):
        if tried >= per_tick:
            log.info("backfills: %d profile(s) left for the next tick", len(due) - i)
            break
        with (
            sessions() as s,
            advisory_lock(
                s.get_bind(), PROFILE_LOCK_NAMESPACE, profile_lock_key(pid)
            ) as got,
        ):
            if not got:
                continue  # another worker is on it
            p = s.get(Profile, pid)
            requested = p.backfill_requested_at if p is not None else None
            if p is None or requested is None or requested > at - BACKFILL_DEBOUNCE:
                continue  # done by another worker, or edited again just now
            attempts = p.backfill_attempts + 1
            ran = p.active
            if ran:
                tried += 1
            try:
                if ran:
                    stats = service.backfill_profile(s, pid, deps=deps, now=at)
                    log.info("backfill profile %s: %s", pid, stats.summary())
                _clear(s, pid, requested, None)
                s.commit()
                if ran:
                    done.append(pid)
            except Exception:
                s.rollback()
                log.exception("backfill failed for profile %s", pid)
                try:
                    _record_failure(s, pid, requested, attempts, at, max_attempts)
                    s.commit()
                except sa.exc.SQLAlchemyError:
                    s.rollback()
                    log.exception("could not push back profile %s", pid)
    return done
