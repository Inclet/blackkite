"""Feed, shortlist and state changes for one caller (docs/api-contract.md section 2)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session

from blackkite.db.models import (
    DigestSetting,
    Opportunity,
    OpportunitySource,
    Source,
    User,
    UserOpportunity,
)
from blackkite.member import schemas as S
from blackkite.member.view import (
    CLOSED_STATUSES,
    FIT_RANK,
    SCORED_STREAMS,
    SHORTLIST_STATES,
    Row,
    closing_soonest,
    current_status,
    feed_item,
    first_name,
    fit_for,
    get_visible,
    is_closed,
    kigali_today,
    load_rows,
    member_visible,
    not_only_muted,
    sort_date,
    sources_checked,
)
from blackkite.pipeline.visibility import visible_source_link

# Upper bound on one feed response (v1 volume is far below it).
FEED_LIMIT = 500


@dataclass(frozen=True, slots=True)
class FeedFilters:
    stream: str | None = None
    profile_id: uuid.UUID | None = None
    # Deadline window: items whose deadline (events: first day) is within this
    # many days from today, Kigali calendar. Undated items are left out.
    window: int | None = None
    verification: str | None = None
    source_id: uuid.UUID | None = None
    # One state; when unset, dismissed items are left out.
    state: str | None = None
    # Current statuses (view.current_status). Unset: open and closing soon.
    # Closed statuses (expired, awarded, cancelled) list only the caller's own
    # tracked items (saved, acting, done) and own private items: an untracked
    # closed item is hard-filtered ("deadline passed", spec 7) and never shown.
    statuses: tuple[str, ...] | None = None
    # At least this fit word (strong > good > possible). Items without one
    # (events, investments, not scored, closed) are left out when set.
    fit: str | None = None


def _state_clause(user_id: uuid.UUID, state: str | None) -> sa.ColumnElement[bool]:
    mine = sa.select(UserOpportunity.opportunity_id).where(
        UserOpportunity.user_id == user_id
    )
    if state is None:
        return Opportunity.id.not_in(mine.where(UserOpportunity.state == "dismissed"))
    if state == "unseen":
        return Opportunity.id.not_in(mine.where(UserOpportunity.state != "unseen"))
    return Opportunity.id.in_(mine.where(UserOpportunity.state == state))


def _base_query(user: User, f: FeedFilters) -> sa.Select:
    q = sa.select(Opportunity).where(
        member_visible(user.id),
        not_only_muted(user.id),
        _state_clause(user.id, f.state),
    )
    if f.state is None and f.statuses is None:
        # Closed items are hard-filtered ("deadline passed", spec 7); an explicit
        # state filter (for example done) still shows them.
        q = q.where(Opportunity.status.not_in(CLOSED_STATUSES))
    if f.stream:
        q = q.where(Opportunity.stream == f.stream)
    if f.verification:
        q = q.where(Opportunity.verification == f.verification)
    if f.source_id:
        q = q.where(
            Opportunity.id.in_(
                sa.select(OpportunitySource.opportunity_id)
                .join(Source, Source.id == OpportunitySource.source_id)
                .where(
                    OpportunitySource.source_id == f.source_id, visible_source_link()
                )
            )
        )
    return q


def _in_window(opps: list[Opportunity], window: int, now: datetime) -> list:
    today = kigali_today(now)
    last = today + timedelta(days=window)
    return [o for o in opps if (d := sort_date(o)) is not None and today <= d <= last]


def _tracked_or_own(row: Row, user_id: uuid.UUID) -> bool:
    return row.state in KEPT_STATES or (
        row.opp.visibility == "private" and row.opp.owner_user_id == user_id
    )


def _at_least(fit: str | None, wanted: str) -> bool:
    return fit in FIT_RANK and FIT_RANK[fit] >= FIT_RANK[wanted]


def feed_rows(db: Session, user: User, f: FeedFilters, now: datetime) -> list[Row]:
    opps = list(db.scalars(_base_query(user, f)).all())
    if f.statuses is not None:
        opps = [o for o in opps if current_status(o, now) in f.statuses]
    elif f.state is None:
        opps = [o for o in opps if not is_closed(o, now)]
    if f.window is not None:
        opps = _in_window(opps, f.window, now)
    if f.statuses is not None:
        open_opps = [o for o in opps if not is_closed(o, now)]
        closed_opps = [o for o in opps if is_closed(o, now)]
    else:
        open_opps, closed_opps = opps, []
    rows = load_rows(db, user, open_opps, profile_id=f.profile_id)
    if closed_opps:
        # Closed items the caller tracks keep their deadline-passed rows.
        rows += [
            r
            for r in load_rows(db, user, closed_opps, keep_filtered=True)
            if _tracked_or_own(r, user.id)
        ]
    rows = [r for r in rows if not _hidden_without_fit_word(r, user.id)]
    if f.fit is not None:
        rows = [r for r in rows if _at_least(fit_for(r, now), f.fit)]
    return closing_soonest(rows, now)[:FEED_LIMIT]


# States that keep an item in the feed even with no fit word (decision 41).
KEPT_STATES = ("saved", "acting", "done")


def _hidden_without_fit_word(row: Row, user_id: uuid.UUID) -> bool:
    """Decision 41: a tender or funding item whose best active-profile row has no
    fit word (scored below "possible", or not scored yet) stays out of the feed,
    unless the caller has saved it, is acting on it or has done it, or it is
    the caller's own private item. Events and investments never carry a fit
    word and are unaffected."""
    if row.opp.stream not in SCORED_STREAMS:
        return False
    if row.opp.visibility == "private" and row.opp.owner_user_id == user_id:
        return False
    if row.state in KEPT_STATES:
        return False
    return row.best is None or row.best.fit_word is None


def feed_content(
    db: Session, user: User, f: FeedFilters, now: datetime
) -> S.FeedContent:
    channel = db.scalar(
        sa.select(DigestSetting.channel)
        .where(DigestSetting.user_id == user.id)
        .order_by(DigestSetting.created_at)
        .limit(1)
    )
    return S.FeedContent(
        user=S.FeedUser(name=first_name(user)),
        sources=sources_checked(db, now),
        digest=S.FeedDigest(channel=channel or "email"),
        items=[feed_item(r, now) for r in feed_rows(db, user, f, now)],
    )


def shortlist(db: Session, user: User, now: datetime) -> list[S.FeedItem]:
    """Saved and acting items, soonest first (closed ones last)."""
    opps = db.scalars(
        sa.select(Opportunity).where(
            member_visible(user.id),
            Opportunity.id.in_(
                sa.select(UserOpportunity.opportunity_id).where(
                    UserOpportunity.user_id == user.id,
                    UserOpportunity.state.in_(SHORTLIST_STATES),
                )
            ),
        )
    ).all()
    rows = load_rows(db, user, opps, keep_filtered=True)
    return [feed_item(r, now) for r in closing_soonest(rows, now)]


def one_row(db: Session, user: User, opportunity_id: uuid.UUID) -> Row | None:
    opp = get_visible(db, user, opportunity_id)
    if opp is None:
        return None
    return load_rows(db, user, [opp], keep_filtered=True)[0]


def _user_opportunity(db: Session, user: User, opp: Opportunity) -> UserOpportunity:
    uo = db.scalar(
        sa.select(UserOpportunity).where(
            UserOpportunity.user_id == user.id,
            UserOpportunity.opportunity_id == opp.id,
        )
    )
    if uo is None:
        uo = UserOpportunity(user_id=user.id, opportunity_id=opp.id, state="unseen")
        db.add(uo)
    return uo


def set_state(
    db: Session, user: User, opportunity_id: uuid.UUID, body: S.StateIn
) -> UserOpportunity | None:
    """Per (user, opportunity), across profiles (decision 19). None if the caller
    cannot see the item: never write state onto someone else's private item."""
    opp = get_visible(db, user, opportunity_id)
    if opp is None:
        return None
    uo = _user_opportunity(db, user, opp)
    uo.state = body.state
    uo.dismiss_reason = body.dismiss_reason if body.state == "dismissed" else None
    db.flush()
    return uo


def set_note(
    db: Session, user: User, opportunity_id: uuid.UUID, body: S.NoteIn
) -> UserOpportunity | None:
    opp = get_visible(db, user, opportunity_id)
    if opp is None:
        return None
    uo = _user_opportunity(db, user, opp)
    uo.note = (body.note or "").strip() or None
    db.flush()
    return uo


def state_out(uo: UserOpportunity) -> S.UserStateOut:
    return S.UserStateOut(
        opportunity_id=str(uo.opportunity_id),
        state=uo.state,
        dismiss_reason=S.dismiss_reason_out(uo.dismiss_reason),
        note=uo.note,
        updated_at=uo.updated_at,
    )
