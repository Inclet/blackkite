"""Source registry (spec 3, 4.1, 4.3, 4.4): status graph, promotion gate, health, stats.

Status graph (spec 4.1 ``suggested -> testing -> active -> paused / retired``)::

    suggested -> testing | retired
    testing   -> active* | paused | retired
    active    -> paused | retired | testing
    paused    -> active* | testing | retired
    retired   -> testing

    * -> active only after at least PROMOTE_MIN_RUNS (2) runs that succeeded AND
      found at least one item, started after the last config change (spec 4.3 step 4).

Health (spec 4.4), from the source's last 3 finished runs (running ones ignored):

    unknown   no finished run yet (cannot happen for an active source)
    failing   the latest finished run failed and so did the one before it,
              or the only finished run failed
    degraded  otherwise, if any of the last 3 failed, or the latest succeeded but
              found 0 items
    ok        otherwise (last 3 all succeeded, latest found items)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from blackkite.db.models import (
    Opportunity,
    OpportunitySource,
    Source,
    SourceRun,
    SourceSuggestion,
    User,
    UserSourceMute,
)

ALLOWED: dict[str, frozenset[str]] = {
    "suggested": frozenset({"testing", "retired"}),
    "testing": frozenset({"active", "paused", "retired"}),
    "active": frozenset({"paused", "retired", "testing"}),
    "paused": frozenset({"active", "testing", "retired"}),
    "retired": frozenset({"testing"}),
}
PROMOTE_MIN_RUNS = 2
HEALTH_WINDOW = 3
ITEMS_WINDOW_DAYS = 30
# Statuses the scheduler runs (spec 5 stage 1).
SCHEDULED_STATUSES = ("active", "testing")
# Items carried only by sources in these statuses are hidden from members (4.3 step 3).
HIDDEN_FROM_MEMBERS = ("suggested", "testing")


class TransitionError(Exception):
    pass


class PromotionBlocked(TransitionError):
    pass


def now_utc() -> datetime:
    return datetime.now(UTC)


# --- schedule -----------------------------------------------------------------------


def parse_schedule(expr: str) -> CronTrigger:
    """Cron text (5 fields, UTC) -> trigger. Raises ValueError."""
    expr = expr.strip()
    if len(expr.split()) != 5:
        raise ValueError("schedule must be a 5-field cron expression")
    try:
        return CronTrigger.from_crontab(expr, timezone=UTC)
    except ValueError as e:
        raise ValueError(f"invalid cron expression: {e}") from None


# --- status -------------------------------------------------------------------------


def qualifying_runs(db: Session, source: Source) -> int:
    """Runs that count toward promotion: succeeded, found items, after config change."""
    q = sa.select(sa.func.count()).where(
        SourceRun.source_id == source.id,
        SourceRun.status == "succeeded",
        SourceRun.items_found > 0,
    )
    if source.config_changed_at is not None:
        q = q.where(SourceRun.started_at >= source.config_changed_at)
    return db.scalar(q) or 0


def change_status(db: Session, source: Source, new: str) -> Source:
    old = source.status
    if new == old:
        return source
    if new not in ALLOWED.get(old, frozenset()):
        raise TransitionError(f"cannot move a source from {old} to {new}")
    if new == "active":
        n = qualifying_runs(db, source)
        if n < PROMOTE_MIN_RUNS:
            raise PromotionBlocked(
                f"needs {PROMOTE_MIN_RUNS} successful runs that found items since its "
                f"config last changed; has {n}"
            )
    source.status = new
    db.flush()
    return source


# --- health and stats ------------------------------------------------------------------


@dataclass(frozen=True)
class SourceStats:
    health: str  # ok | degraded | failing | unknown
    last_success_at: datetime | None
    last_run_at: datetime | None
    items_30d: int


def health_from_runs(runs: list[tuple[str, int]]) -> str:
    """``runs``: (status, items_found) of finished runs, newest first."""
    runs = runs[:HEALTH_WINDOW]
    if not runs:
        return "unknown"
    statuses = [s for s, _ in runs]
    if statuses[0] == "failed" and (len(statuses) == 1 or statuses[1] == "failed"):
        return "failing"
    if "failed" in statuses or runs[0][1] == 0:
        return "degraded"
    return "ok"


def source_stats(
    db: Session, source_ids: list[uuid.UUID], now: datetime | None = None
) -> dict[uuid.UUID, SourceStats]:
    if not source_ids:
        return {}
    now = now or now_utc()
    rn = (
        sa.func.row_number()
        .over(partition_by=SourceRun.source_id, order_by=SourceRun.started_at.desc())
        .label("rn")
    )
    recent = (
        sa.select(SourceRun.source_id, SourceRun.status, SourceRun.items_found, rn)
        .where(SourceRun.source_id.in_(source_ids), SourceRun.status != "running")
        .subquery()
    )
    runs: dict[uuid.UUID, list[tuple[str, int]]] = {i: [] for i in source_ids}
    for sid, status, found, _ in db.execute(
        sa.select(recent).where(recent.c.rn <= HEALTH_WINDOW).order_by(recent.c.rn)
    ):
        runs[sid].append((status, found))

    last_success = dict(
        db.execute(
            sa.select(SourceRun.source_id, sa.func.max(SourceRun.finished_at))
            .where(SourceRun.source_id.in_(source_ids), SourceRun.status == "succeeded")
            .group_by(SourceRun.source_id)
        ).all()
    )
    last_run = dict(
        db.execute(
            sa.select(SourceRun.source_id, sa.func.max(SourceRun.started_at))
            .where(SourceRun.source_id.in_(source_ids))
            .group_by(SourceRun.source_id)
        ).all()
    )
    # Items found in the last 30 days: distinct catalogue items this source carried
    # (opportunity_source.last_seen within the window).
    items = dict(
        db.execute(
            sa.select(
                OpportunitySource.source_id,
                sa.func.count(sa.distinct(OpportunitySource.opportunity_id)),
            )
            .where(
                OpportunitySource.source_id.in_(source_ids),
                OpportunitySource.last_seen >= now - timedelta(days=ITEMS_WINDOW_DAYS),
            )
            .group_by(OpportunitySource.source_id)
        ).all()
    )
    return {
        i: SourceStats(
            health=health_from_runs(runs[i]),
            last_success_at=last_success.get(i),
            last_run_at=last_run.get(i),
            items_30d=items.get(i, 0),
        )
        for i in source_ids
    }


# --- member views ----------------------------------------------------------------------


def member_sources(db: Session) -> list[Source]:
    return list(
        db.scalars(
            sa.select(Source).where(Source.status == "active").order_by(Source.name)
        )
    )


def muted_ids(db: Session, user: User) -> set[uuid.UUID]:
    return set(
        db.scalars(
            sa.select(UserSourceMute.source_id).where(UserSourceMute.user_id == user.id)
        )
    )


def mute(db: Session, user: User, source: Source) -> None:
    from sqlalchemy.dialects.postgresql import insert

    db.execute(
        insert(UserSourceMute)
        .values(user_id=user.id, source_id=source.id)
        .on_conflict_do_nothing()
    )


def unmute(db: Session, user: User, source_id: uuid.UUID) -> None:
    db.execute(
        sa.delete(UserSourceMute).where(
            UserSourceMute.user_id == user.id, UserSourceMute.source_id == source_id
        )
    )


def member_visible_opportunity(user_id: uuid.UUID) -> sa.ColumnElement[bool]:
    """WHERE clause for opportunities a member may see.

    Public items, unless every source that carries them is still `testing` or
    `suggested` (spec 4.3 step 3); public items with no source row (e.g. a manual
    item promoted with consent) stay visible. Private items: owner only.
    """
    visible_source = sa.exists().where(
        OpportunitySource.opportunity_id == Opportunity.id,
        OpportunitySource.source_id == Source.id,
        Source.status.not_in(HIDDEN_FROM_MEMBERS),
    )
    any_source = sa.exists().where(OpportunitySource.opportunity_id == Opportunity.id)
    return sa.or_(
        sa.and_(
            Opportunity.visibility == "public", sa.or_(visible_source, ~any_source)
        ),
        sa.and_(
            Opportunity.visibility == "private", Opportunity.owner_user_id == user_id
        ),
    )


def member_visible_source_link() -> sa.ColumnElement[bool]:
    """WHERE clause on opportunity_source joined to source: links members may see."""
    return Source.status.not_in(HIDDEN_FROM_MEMBERS)


# --- suggestions ---------------------------------------------------------------------


def review_suggestion(
    db: Session, suggestion: SourceSuggestion, admin: User, decision: str
) -> SourceSuggestion:
    if decision not in ("accepted", "rejected"):
        raise ValueError(decision)
    if suggestion.status != "suggested":
        raise TransitionError(f"suggestion already {suggestion.status}")
    suggestion.status = decision
    suggestion.reviewed_by = admin.id
    suggestion.reviewed_at = now_utc()
    db.flush()
    return suggestion
