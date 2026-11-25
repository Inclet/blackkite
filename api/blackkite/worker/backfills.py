"""Worker job: run pending profile backfills (scoring/backfill.py).

Every tick, profiles whose newest request is at least ``BACKFILL_DEBOUNCE`` old
are backfilled one at a time, each under a Postgres advisory lock per profile
(two workers never score the same profile at once). The request is cleared only
if no newer one arrived during the run; otherwise the profile runs again once
the newer request is old enough. An inactive profile's request is just cleared
(activation asks again if needed). A failure leaves the request in place, pushed
back by one debounce period, and never stops the other profiles.
"""

from __future__ import annotations

import logging
import uuid
import zlib
from collections.abc import Callable
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from blackkite.db.models import Profile
from blackkite.scoring.backfill import BACKFILL_DEBOUNCE
from blackkite.worker.runner import advisory_lock

log = logging.getLogger("blackkite.worker")

# Advisory lock namespace for profile backfills ("BP"); key: crc32 of the id.
PROFILE_LOCK_NAMESPACE = 0x4250


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
    session: Session, profile_id: uuid.UUID, requested: datetime, to: datetime | None
) -> None:
    session.execute(
        sa.update(Profile)
        .where(Profile.id == profile_id, Profile.backfill_requested_at == requested)
        .values(backfill_requested_at=to, updated_at=Profile.updated_at)
        .execution_options(synchronize_session=False)
    )


def run_pending_backfills(
    sessions: sessionmaker[Session],
    now: Callable[[], datetime] = _now,
    deps=None,
) -> list[uuid.UUID]:
    """Backfill every due profile. Returns the ids actually backfilled."""
    from blackkite.scoring import service

    at = now()
    with sessions() as s:
        due = due_backfills(s, at)
    done: list[uuid.UUID] = []
    if not due:
        return done
    deps = deps or service.default_deps()
    for pid in due:
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
            if requested is None or requested > at - BACKFILL_DEBOUNCE:
                continue  # done by another worker, or edited again just now
            try:
                ran = p.active
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
                    _clear(s, pid, requested, at)
                    s.commit()
                except sa.exc.SQLAlchemyError:
                    s.rollback()
                    log.exception("could not push back profile %s", pid)
    return done
