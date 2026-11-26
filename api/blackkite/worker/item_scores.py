"""Worker job: score queued items (``opportunity.score_requested_at``).

A private manual item asks to be scored when its owner creates or edits it
(member/items.py), and is scored for its owner only; a published item asks
when an admin makes it public, and is scored for everyone (``scoring.service.
score_opportunities``). Nothing is scored in the HTTP request (spec 5 cost
guard).

One worker at a time (an advisory lock). At most ``per_tick`` items a tick,
oldest request first. A request is cleared only if no newer one arrived during
the run (an edit meanwhile is scored on the next tick). A failure leaves the
batch queued, pushed back ``RETRY_AFTER``; it never stops the tick. Clearing
leaves ``updated_at`` alone, so scoring's judgement reuse still holds.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from blackkite.db.models import Opportunity
from blackkite.worker.runner import advisory_lock

log = logging.getLogger("blackkite.worker")

# Advisory lock for the item queue ("IS").
ITEM_SCORE_LOCK = (0x4953, 1)
DEFAULT_PER_TICK = 50
RETRY_AFTER = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(UTC)


def request_scoring(opp: Opportunity, now: datetime) -> None:
    """Queue one item (ORM object, saved by the caller's commit)."""
    opp.score_requested_at = now


def due(
    session: Session, now: datetime, limit: int
) -> list[tuple[uuid.UUID, datetime]]:
    return list(
        session.execute(
            sa.select(Opportunity.id, Opportunity.score_requested_at)
            .where(Opportunity.score_requested_at <= now)
            .order_by(Opportunity.score_requested_at, Opportunity.id)
            .limit(limit)
        ).all()
    )  # type: ignore[arg-type]


def _set(session: Session, oid: uuid.UUID, requested: datetime, to) -> None:
    session.execute(
        sa.update(Opportunity)
        .where(Opportunity.id == oid, Opportunity.score_requested_at == requested)
        .values(score_requested_at=to, updated_at=Opportunity.updated_at)
        .execution_options(synchronize_session=False)
    )


def run_pending_item_scores(
    sessions: sessionmaker[Session],
    now: Callable[[], datetime] = _now,
    deps=None,
    *,
    per_tick: int = DEFAULT_PER_TICK,
) -> list[uuid.UUID]:
    """Score up to ``per_tick`` queued items. Returns the ids scored."""
    from blackkite.scoring import service

    at = now()
    with sessions() as s, advisory_lock(s.get_bind(), *ITEM_SCORE_LOCK) as got:
        if not got:
            return []
        batch = due(s, at, per_tick)
        if not batch:
            return []
        ids = [oid for oid, _ in batch]
        try:
            stats = service.score_opportunities(
                s, ids, deps=deps or service.default_deps(), now=at
            )
            for oid, requested in batch:
                _set(s, oid, requested, None)
            s.commit()
        except Exception:
            s.rollback()
            log.exception("scoring %d queued item(s) failed", len(ids))
            try:
                for oid, requested in batch:
                    _set(s, oid, requested, at + RETRY_AFTER)
                s.commit()
            except sa.exc.SQLAlchemyError:
                s.rollback()
                log.exception("could not push back queued items")
            return []
    log.info("item scores: %d item(s): %s", len(ids), stats.summary())
    return ids
