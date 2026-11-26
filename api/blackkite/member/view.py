"""Per-user views of the catalogue: what a caller may see, with their state and
best score, as the member API's ``FeedItem`` (docs/api-contract.md section 2).

Isolation (spec 6, spec 10): every query here takes the caller's id; per-user
tables are always filtered by it, and catalogue rows go through
``pipeline/visibility.py``. Member routes use the **member** rule for everyone,
admins included: items carried only by testing sources stay out of feeds, the
opportunity page, the shortlist and digests (spec 4.3 step 3). Admins see those
in the admin catalogue (routes/catalogue.py). Another user's private item is
never visible, so it 404s on every member route.

Scores (contract section 1): one ``user_opportunity_score`` row per profile; a
row with ``score_breakdown.hard_filtered`` set is never shown. The item's best
profile is the highest-scoring non-filtered row among the user's active
profiles. An item whose every row is filtered is left out of lists.

A ``muted_source_only`` row on an item that is no longer carried only by sources
the user mutes (an unmute the worker has not rescored yet) counts as not scored:
not filtered, never the best row. So the item is unscored at once: it opens
and shows on the shortlist; a tender or funding item stays out of the feed until
rescored (decision 41, member/feed.py).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

import sqlalchemy as sa
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from blackkite.db.models import (
    ChangeEvent,
    Document,
    Opportunity,
    OpportunitySource,
    Profile,
    Source,
    SourceRun,
    User,
    UserOpportunity,
    UserOpportunityScore,
    UserSourceMute,
)
from blackkite.member import schemas as S
from blackkite.member.trust import LinkInfo, trust_copy
from blackkite.pipeline.dates import KIGALI, kigali_date
from blackkite.pipeline.validate import status_for, trust_state
from blackkite.pipeline.visibility import (
    MEMBER_VISIBLE_SOURCE_STATUSES,
    carried_by_visible_source,
    own_private,
    published_manual,
    visible_source_link,
    visible_to,
)
from blackkite.scoring.service import NO_MODEL_REASON

CLOSED_STATUSES = ("expired", "awarded", "cancelled")
# Streams that show a fit word; events and investments never do (decision 24).
SCORED_STREAMS = ("tender", "funding")
FIT_WORDS = ("strong", "good", "possible")
# Order of fit words for comparisons (alerts: "at least good"); no word ranks 0.
FIT_RANK = {"possible": 1, "good": 2, "strong": 3}
SHORTLIST_STATES = ("saved", "acting")
TO_CHECK_PREFIX = "To check: "


# --- scores -------------------------------------------------------------------------


def _is_no_model(reason: str) -> bool:
    return reason.strip().rstrip(".") == NO_MODEL_REASON.rstrip(".")


@dataclass(frozen=True, slots=True)
class ScoreView:
    profile_id: uuid.UUID
    profile_name: str
    score: int | None
    breakdown: dict[str, Any]
    reason: str | None

    @property
    def hard_filtered(self) -> str | None:
        return self.breakdown.get("hard_filtered")

    @property
    def fit_word(self) -> str | None:
        w = self.breakdown.get("fit_word")
        return w if w in FIT_WORDS else None

    @property
    def reasons(self) -> list[str]:
        """The reasons shown to the member. A rules-only score's "Scored without
        the model" says nothing about the item, so only its rules reasons show."""
        rs = [r for r in self.breakdown.get("reasons") or [] if isinstance(r, str)]
        if not rs and self.reason:
            rs = [self.reason]
        return [r for r in rs if not _is_no_model(r)]

    @property
    def flags(self) -> list[dict[str, Any]]:
        return [f for f in self.breakdown.get("flags") or [] if isinstance(f, dict)]

    @property
    def provisional(self) -> bool:
        """The profile was scored as provisional (spec 7.1: AI lab's default set)."""
        return self.breakdown.get("provisional") is True

    @property
    def one_line_reason(self) -> str | None:
        """The reason for digests and alerts. A rules-only score's reason ("Scored
        without the model") says nothing about the item, so the first rules
        reason that names the match is used instead."""
        if self.reason and not _is_no_model(self.reason):
            return self.reason
        return next(iter(self.reasons), None)

    @property
    def rank(self) -> int:
        return self.score if self.score is not None else -1


@dataclass(slots=True)
class Row:
    """One opportunity as one user sees it."""

    opp: Opportunity
    uo: UserOpportunity | None
    best: ScoreView | None
    all_filtered: bool
    links: list[LinkInfo] = field(default_factory=list)

    @property
    def state(self) -> str:
        return self.uo.state if self.uo else "unseen"


# --- visibility -------------------------------------------------------------------------


def member_visible(user_id: uuid.UUID) -> ColumnElement[bool]:
    """What a member route may show this caller (admins get the member rule too)."""
    return visible_to(user_id, is_admin=False)


def not_only_muted(user_id: uuid.UUID) -> ColumnElement[bool]:
    """Hard filter "muted source only" (spec 7) at query time: a public item stays
    while at least one member-visible source carrying it is not muted by the user."""
    muted = sa.select(UserSourceMute.source_id).where(UserSourceMute.user_id == user_id)
    unmuted_carrier = sa.exists(
        sa.select(sa.literal(1))
        .select_from(OpportunitySource)
        .join(Source, Source.id == OpportunitySource.source_id)
        .where(
            OpportunitySource.opportunity_id == Opportunity.id,
            Source.status.in_(MEMBER_VISIBLE_SOURCE_STATUSES),
            OpportunitySource.source_id.not_in(muted),
        )
    )
    # A published manual item no visible source carries has nothing to mute.
    uncarried_manual = sa.and_(published_manual(), ~carried_by_visible_source())
    return sa.or_(own_private(user_id), unmuted_carrier, uncarried_manual)


MUTED_SOURCE_ONLY = "muted_source_only"


def _unmuted(db: Session, user_id: uuid.UUID, opp_ids: Iterable[uuid.UUID]) -> set:
    """Of ``opp_ids``, the items the user's mutes no longer hide."""
    ids = list(opp_ids)
    if not ids:
        return set()
    return set(
        db.scalars(
            sa.select(Opportunity.id).where(
                Opportunity.id.in_(ids), not_only_muted(user_id)
            )
        )
    )


def get_visible(
    db: Session, user: User, opportunity_id: uuid.UUID
) -> Opportunity | None:
    """The opportunity if this caller may see it, else None (routes answer 404)."""
    return db.scalar(
        sa.select(Opportunity).where(
            Opportunity.id == opportunity_id, member_visible(user.id)
        )
    )


# --- loading ------------------------------------------------------------------------------


def _links(
    db: Session, opp_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[LinkInfo]]:
    out: dict[uuid.UUID, list[LinkInfo]] = defaultdict(list)
    if not opp_ids:
        return out
    rows = db.execute(
        sa.select(OpportunitySource, Source.name, Source.publisher)
        .join(Source, Source.id == OpportunitySource.source_id)
        .where(OpportunitySource.opportunity_id.in_(opp_ids), visible_source_link())
        .order_by(OpportunitySource.first_seen, Source.name)
    ).all()
    for link, name, publisher in rows:
        out[link.opportunity_id].append(
            LinkInfo(
                source_name=name,
                publisher=publisher,
                url=link.url,
                is_original=link.is_original,
                first_seen=link.first_seen,
                last_seen=link.last_seen,
            )
        )
    return out


def _scores(
    db: Session, user_id: uuid.UUID, opp_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[ScoreView]]:
    out: dict[uuid.UUID, list[ScoreView]] = defaultdict(list)
    if not opp_ids:
        return out
    rows = db.execute(
        sa.select(UserOpportunityScore, Profile.name)
        .join(
            Profile,
            sa.and_(
                Profile.id == UserOpportunityScore.profile_id,
                Profile.user_id == UserOpportunityScore.user_id,
            ),
        )
        .where(
            UserOpportunityScore.user_id == user_id,
            Profile.user_id == user_id,
            Profile.active.is_(True),
            UserOpportunityScore.opportunity_id.in_(opp_ids),
        )
    ).all()
    for s, name in rows:
        out[s.opportunity_id].append(
            ScoreView(
                profile_id=s.profile_id,
                profile_name=name,
                score=s.score,
                breakdown=s.score_breakdown or {},
                reason=s.score_reason,
            )
        )
    return out


def _states(
    db: Session, user_id: uuid.UUID, opp_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, UserOpportunity]:
    if not opp_ids:
        return {}
    rows = db.scalars(
        sa.select(UserOpportunity).where(
            UserOpportunity.user_id == user_id,
            UserOpportunity.opportunity_id.in_(opp_ids),
        )
    )
    return {r.opportunity_id: r for r in rows}


def load_rows(
    db: Session,
    user: User,
    opps: Iterable[Opportunity],
    *,
    profile_id: uuid.UUID | None = None,
    keep_filtered: bool = False,
    keep_own: bool = False,
) -> list[Row]:
    """Attach the caller's state, best score and visible sources to each item.

    Items whose every score row is hard-filtered are dropped unless
    ``keep_filtered``. With ``profile_id``, only that profile's row counts, and
    items it did not score (or filtered) are dropped.

    ``keep_own`` (feed and calendar; orchestrator decision 2026-11-26): the
    caller's own private items are never dropped for hard filters (stream not
    selected, outside Rwanda, below minimum value, ...); with ``profile_id``
    they stay when that profile scored them at all, filtered or not. Digests
    and alerts do not pass it: they still need a fit word.
    """
    opps = list(opps)
    ids = [o.id for o in opps]
    scores = _scores(db, user.id, ids)
    states = _states(db, user.id, ids)
    links = _links(db, ids)
    stale = _unmuted(
        db,
        user.id,
        {
            oid
            for oid, rs in scores.items()
            if any(r.hard_filtered == MUTED_SOURCE_ONLY for r in rs)
        },
    )
    out: list[Row] = []
    for o in opps:
        rows = scores.get(o.id, [])
        if profile_id is not None:
            rows = [r for r in rows if r.profile_id == profile_id]
        pending = False
        if o.id in stale:  # unmuted since scored: these rows wait for the worker
            pending = any(r.hard_filtered == MUTED_SOURCE_ONLY for r in rows)
            rows = [r for r in rows if r.hard_filtered != MUTED_SOURCE_ONLY]
        shown = [r for r in rows if not r.hard_filtered]
        all_filtered = bool(rows) and not shown and not pending
        own = keep_own and o.visibility == "private" and o.owner_user_id == user.id
        if (
            profile_id is not None
            and not shown
            and not keep_filtered
            and not (own and rows)
        ):
            continue
        if all_filtered and not keep_filtered and not own:
            continue
        best = max(shown, key=lambda r: (r.rank, r.profile_name)) if shown else None
        out.append(Row(o, states.get(o.id), best, all_filtered, links.get(o.id, [])))
    return out


# --- dates ------------------------------------------------------------------------------


def end_of(opp: Opportunity) -> datetime | None:
    """The moment the item stops being actionable (validate.status_for's rule)."""
    if opp.deadline_at is not None:
        return opp.deadline_at
    if opp.stream == "event":
        return opp.event_end or opp.event_start
    return None


def is_closed(opp: Opportunity, now: datetime) -> bool:
    if opp.status in CLOSED_STATUSES:
        return True
    end = end_of(opp)
    return end is not None and end < now


def current_status(opp: Opportunity, now: datetime) -> str:
    """The item's status now: a stored closed status stands; otherwise it is
    worked out from its dates (the stored one moves on once a day)."""
    if opp.status in CLOSED_STATUSES:
        return opp.status
    return status_for(
        opp.status, opp.stream, opp.deadline_at, opp.event_start, opp.event_end, now
    )


def uses_event_dates(opp: Opportunity) -> bool:
    return opp.stream == "event" and opp.event_start is not None


def sort_date(opp: Opportunity) -> date | None:
    """The date lists are ordered by: an event's first day, else the deadline."""
    if uses_event_dates(opp):
        return kigali_date(opp.event_start)  # type: ignore[arg-type]
    return kigali_date(opp.deadline_at) if opp.deadline_at else None


def closing_soonest(rows: list[Row], now: datetime) -> list[Row]:
    """Open items by date, undated after them, closed items last (as the web's
    sortClosingSoonest); then best score, then title."""

    def key(r: Row) -> tuple[Any, ...]:
        d = sort_date(r.opp)
        rank = 2 if is_closed(r.opp, now) else (1 if d is None else 0)
        return (rank, d or date.max, -(r.best.rank if r.best else -1), r.opp.title)

    return sorted(rows, key=key)


def kigali_today(now: datetime) -> date:
    return now.astimezone(KIGALI).date()


# --- FeedItem ---------------------------------------------------------------------------


def _topic(opp: Opportunity) -> str | None:
    for tag in opp.tags or []:
        if tag.startswith("sector:"):
            label = tag.split(":", 1)[1].strip()
            if label:
                return label[0].upper() + label[1:]
    return None


def _original_url(row: Row) -> str:
    if not row.links:
        # A manual item's own link (spec 6); else nothing.
        return row.opp.manual_url or ""
    original = next((link for link in row.links if link.is_original), None)
    return (original or row.links[0]).url


def _to_check(best: ScoreView | None) -> str | None:
    if best is None or not best.flags:
        return None
    text = best.flags[0].get("to_check")
    if not isinstance(text, str) or not text.strip():
        return None
    text = text.strip()
    return text if text.startswith("To check") else TO_CHECK_PREFIX + text


def _top_flag(best: ScoreView | None, fit: str | None) -> str | None:
    """The first flag's label, sent only for a "good" fit (contract section 2):
    the row subtitle then reads "Good fit · <flag>" (develoPPP board). A strong
    item keeps its organisation in the subtitle; its flag shows as To check."""
    if fit != "good" or best is None or not best.flags:
        return None
    label = best.flags[0].get("label")
    return label if isinstance(label, str) and label.strip() else None


def trust_for(row: Row) -> S.Trust:
    o = row.opp
    state = (o.evidence or {}).get("_trust") or trust_state(o.verification, o.evidence)
    desktop, phone = trust_copy(
        state,
        stream=o.stream,
        organisation=o.organisation_short or o.organisation,
        published_at=o.published_at,
        deadline_at=o.deadline_at,
        links=row.links,
        private=o.visibility == "private",
    )
    return S.Trust(state=state, desktop=desktop, phone=phone)


def fit_for(row: Row, now: datetime) -> str | None:
    if row.opp.stream not in SCORED_STREAMS or is_closed(row.opp, now):
        return None
    if row.best is not None:
        return row.best.fit_word
    return None if row.all_filtered else "not-scored"


def _item_fields(row: Row, now: datetime) -> dict[str, Any]:
    o = row.opp
    best = row.best
    event_dates = None
    deadline = None
    if uses_event_dates(o):
        event_dates = S.EventDates(
            start=kigali_date(o.event_start).isoformat(),  # type: ignore[arg-type]
            end=kigali_date(o.event_end).isoformat() if o.event_end else None,
        )
    elif o.deadline_at is not None:
        deadline = kigali_date(o.deadline_at).isoformat()
    fit = fit_for(row, now)
    no_deadline = None
    if deadline is None and event_dates is None:
        no_deadline = (
            "No deadline" if o.stream == "investment" else "No deadline stated"
        )
    return {
        "id": str(o.id),
        "stream": o.stream,
        "state": row.state,
        "title": o.title,
        "organisation": o.organisation or "",
        "organisation_short": o.organisation_short,
        "fit": fit,
        "provisional": bool(best and best.provisional),
        "top_flag": _top_flag(best, fit),
        "topic": _topic(o) if o.stream == "event" else None,
        "venue": o.location if o.stream == "event" else None,
        "note": o.value_note if o.stream == "investment" else None,
        "deadline": deadline,
        "event_dates": event_dates,
        "no_deadline_text": no_deadline,
    }


def _detail_fields(row: Row) -> dict[str, Any]:
    best = row.best
    return {
        "profile": best.profile_name if best else None,
        "location": row.opp.location,
        "reasons": best.reasons if best else [],
        "to_check": _to_check(best),
        "trust": trust_for(row),
        "original_url": _original_url(row),
    }


def feed_item(row: Row, now: datetime) -> S.FeedItem:
    return S.FeedItem(
        **_item_fields(row, now), detail=S.FeedItemDetail(**_detail_fields(row))
    )


# --- opportunity page -------------------------------------------------------------------

# Extracted fields shown with their snippets, in page order.
DETAIL_FIELDS = (
    "subtype",
    "organisation",
    "summary",
    "published_at",
    "deadline_at",
    "event_start",
    "event_end",
    "value_amount",
    "value_currency",
    "value_note",
    "location",
    "eligibility",
    "requirements",
    "submission_method",
    "fees",
)


def _json_value(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    if v is None or isinstance(v, (str, int, float, bool, list, dict)):
        return v
    return str(v)


def _fields(opp: Opportunity) -> list[S.FieldOut]:
    ev = opp.evidence or {}
    out: list[S.FieldOut] = []
    for name in DETAIL_FIELDS:
        value = getattr(opp, name)
        if value is None or value == []:
            continue
        e = ev.get(name) if isinstance(ev.get(name), dict) else {}
        if name == "requirements":
            snips = [s for s in e.get("snippets") or [] if isinstance(s, str)]
            out.append(
                S.FieldOut(name="requirements", value=value, snippets=snips or None)
            )
            continue
        snippet = e.get("snippet") if isinstance(e.get("snippet"), str) else None
        out.append(
            S.FieldOut(name=to_camel(name), value=_json_value(value), snippet=snippet)
        )
    return out


def _document_name(d: Document) -> str:
    if d.file_path:
        return PurePosixPath(d.file_path).name
    path = unquote(urlsplit(d.url).path).rstrip("/")
    return PurePosixPath(path).name or urlsplit(d.url).hostname or "document"


def _changes(db: Session, opp_id: uuid.UUID) -> list[S.ChangeOut]:
    """Change history. Values that name a source show its name, and changes
    reported by a source the caller cannot see are left out. Who made a change
    (``reviewed_by``, ``published_by``: admin ids) is not shown to members."""
    visible = {
        str(sid): name
        for sid, name in db.execute(
            sa.select(Source.id, Source.name)
            .join(OpportunitySource, OpportunitySource.source_id == Source.id)
            .where(OpportunitySource.opportunity_id == opp_id, visible_source_link())
        )
    }
    out: list[S.ChangeOut] = []
    for c in db.scalars(
        sa.select(ChangeEvent)
        .where(ChangeEvent.opportunity_id == opp_id)
        .order_by(ChangeEvent.at.desc())
    ):
        hidden = False
        values = []
        for v in (c.old, c.new):
            if isinstance(v, dict) and "source_id" in v:
                name = visible.get(str(v["source_id"]))
                if name is None:
                    hidden = True
                v = {
                    ("source" if k == "source_id" else k): (
                        name if k == "source_id" else x
                    )
                    for k, x in v.items()
                }
            if isinstance(v, dict):
                v = {k: x for k, x in v.items() if not k.endswith("_by")}
            values.append(v)
        if not hidden:
            out.append(
                S.ChangeOut(field=c.field, old=values[0], new=values[1], at=c.at)
            )
    return out


def own_item_out(opp: Opportunity, user_id: uuid.UUID | None) -> S.OwnItem | None:
    """Sharing state of the caller's own manual item (private or published)."""
    if user_id is None or opp.owner_user_id != user_id:
        return None
    if opp.visibility != "private" and opp.made_public_at is None:
        return None
    return S.OwnItem(
        share_consent=opp.share_consent_at is not None,
        published=opp.made_public_at is not None,
    )


def opportunity_out(
    db: Session, row: Row, now: datetime, *, user_id: uuid.UUID | None = None
) -> S.OpportunityOut:
    o = row.opp
    docs = db.scalars(
        sa.select(Document)
        .where(Document.opportunity_id == o.id)
        .order_by(Document.created_at)
    ).all()
    detail = S.OpportunityDetail(
        **_detail_fields(row),
        fields=_fields(o),
        sources=[
            S.SourceLinkOut(
                name=link.source_name,
                url=link.url,
                is_original=link.is_original,
                first_seen=link.first_seen,
                last_seen=link.last_seen,
            )
            for link in row.links
        ],
        documents=[S.DocumentOut(name=_document_name(d)) for d in docs],
        changes=_changes(db, o.id),
        note=row.uo.note if row.uo else None,
        state=row.state,
        dismiss_reason=S.dismiss_reason_out(row.uo.dismiss_reason if row.uo else None),
        own_item=own_item_out(o, user_id),
    )
    return S.OpportunityOut(**_item_fields(row, now), detail=detail)


# --- feed header ----------------------------------------------------------------------


def first_name(user: User) -> str:
    """For the greeting. Empty when no name is set: the greeting then has no
    name ("Good morning"), never a stand-in."""
    name = (user.name or "").strip()
    return name.split()[0] if name else ""


def _when(at: datetime, now: datetime) -> str:
    local = at.astimezone(KIGALI)
    today = kigali_today(now)
    if local.date() == today:
        if local.hour < 12:
            return "this morning"
        return "this afternoon" if local.hour < 18 else "this evening"
    if local.date() == today - timedelta(days=1):
        return "yesterday"
    return f"on {local.day} {local:%b}"


def sources_checked(db: Session, now: datetime) -> S.FeedSources:
    """Active sources with a successful run in the last 24 hours, and when the
    latest of those finished ("8 sources checked this morning")."""
    rows = db.execute(
        sa.select(SourceRun.source_id, sa.func.max(SourceRun.finished_at))
        .join(Source, Source.id == SourceRun.source_id)
        .where(
            Source.status == "active",
            SourceRun.status == "succeeded",
            SourceRun.finished_at >= now - timedelta(hours=24),
        )
        .group_by(SourceRun.source_id)
    ).all()
    if not rows:
        return S.FeedSources(checked=0, when="")
    latest = max(at for _, at in rows)
    return S.FeedSources(checked=len(rows), when=_when(latest, now))
