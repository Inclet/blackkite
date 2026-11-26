"""Procurement records (awards, plan items) from a source run, and their links to
catalogue tenders. Never writes ``opportunity``.

``ingest_records(session, source, records)`` runs the matching ingest path
(``pipeline/awards.py`` or ``pipeline/plans.py``) for every record inside its own
SAVEPOINT (one bad record is counted in ``failed`` and rolled back), then links
new and unlinked rows to tenders. It never commits; the runner owns the
transaction, as for ``ingest_items``.

``link_tender(session, opp)`` runs on every tender the opportunity ingest creates
or updates (``pipeline/ingest.py``): awards and plan items not yet linked are
linked to it when they match, so a plan is dropped from the plans list once its
tender is advertised.

Matching a record to a tender (public tenders only, never a private item):

1. **Tender ref**: the record's ref (at least 5 characters with a digit, so
   "N/A" or "2026" never match) appears in the tender's title or in the text of
   its evidence (every source's listing and the extraction's snippets),
   case-insensitive.
2. **Title and entity**: the procuring entity matches the tender's organisation
   (``dedupe.org_similarity`` >= 85, acronyms included) and the title matches
   (awards: ``token_sort_ratio`` >= 90; plans: ``token_set_ratio`` >= 90, since a
   tender title often wraps the planned description in "Tender for ..."), with
   generic titles ("Invitation for bids", under 16 characters) never matched.
   A plan is matched only to a tender published (or first seen) no earlier than
   180 days before its planned period or fiscal year.

``preview(records, now)`` normalises a test run's records for the admin screen;
it touches no database.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from blackkite.collectors.base import Records
from blackkite.db.models import Award, Opportunity, ProcurementPlanItem, Source
from blackkite.llm.embeddings import Embedder
from blackkite.pipeline import awards as A
from blackkite.pipeline import categories
from blackkite.pipeline import plans as PL
from blackkite.pipeline.dedupe import ORG_MIN, is_generic, org_similarity, title_key
from blackkite.pipeline.procurement import fiscal_start_year, period_label

log = logging.getLogger("blackkite.pipeline")

TITLE_MIN = 90
PLAN_LEAD = timedelta(days=180)
REF_MIN_LEN = 5


@dataclass
class RecordsResult:
    found: int = 0
    new: int = 0
    failed: int = 0
    skipped: int = 0
    warnings: list[dict] = field(default_factory=list)


def ingest_records(
    session: Session,
    source: Source,
    records: Records,
    *,
    now: datetime,
    embedder: Embedder | None = None,
) -> RecordsResult:
    result = RecordsResult(found=len(records.items))
    today = A.today_of(now)
    touched: list[Any] = []
    for raw in records.items:
        try:
            with session.begin_nested():
                if records.kind == "award":
                    n = A.normalise_award(raw, records.formats, today)
                    if n is None:
                        result.skipped += 1
                        continue
                    row, created = A.upsert_award(session, source, n, now)
                else:
                    n = PL.normalise_plan(raw, records.formats, today)
                    if n is None:
                        result.skipped += 1
                        continue
                    row, created = PL.upsert_plan(
                        session, source, n, now, embedder=embedder
                    )
                result.new += created
                if row.opportunity_id is None:
                    touched.append(row)
        except Exception:  # one bad record must not sink the batch
            result.failed += 1
            log.exception("record ingest failed for %s from %s", raw.url, source.id)
    if touched:
        tenders = _candidate_tenders(session)
        for row in touched:
            opp_id = (
                match_award(session, row, tenders)
                if isinstance(row, Award)
                else match_plan(session, row, tenders)
            )
            if opp_id is not None:
                row.opportunity_id = opp_id
    session.flush()
    return result


# --- matching --------------------------------------------------------------------


@dataclass(frozen=True)
class Tender:
    id: uuid.UUID
    titles: tuple[str, ...]
    orgs: tuple[str, ...]
    seen_from: datetime


def _tender_of(opp: Opportunity) -> Tender:
    titles = [opp.title]
    orgs = [o for o in (opp.organisation, opp.organisation_short) if o]
    for entry in (opp.evidence or {}).get("_sources", {}).values():
        if isinstance(entry, dict):
            if entry.get("title"):
                titles.append(entry["title"])
            if entry.get("organisation"):
                orgs.append(entry["organisation"])
    seen = min(d for d in (opp.published_at, opp.created_at) if d is not None)
    return Tender(
        opp.id, tuple(dict.fromkeys(titles)), tuple(dict.fromkeys(orgs)), seen
    )


def _public_tenders():
    return sa.select(Opportunity).where(
        Opportunity.stream == "tender", Opportunity.visibility == "public"
    )


def _candidate_tenders(session: Session) -> list[Tender]:
    return [_tender_of(o) for o in session.scalars(_public_tenders())]


def _usable_ref(ref: str | None) -> bool:
    return bool(ref) and len(ref) >= REF_MIN_LEN and any(c.isdigit() for c in ref)


def _by_ref(session: Session, ref: str | None) -> uuid.UUID | None:
    if not _usable_ref(ref):
        return None
    needle = ref.lower()
    text = sa.func.lower(
        sa.func.concat(Opportunity.title, " ", sa.cast(Opportunity.evidence, sa.Text))
    )
    return session.scalar(
        _public_tenders()
        .with_only_columns(Opportunity.id)
        .where(sa.func.strpos(text, needle) > 0)
        .order_by(Opportunity.created_at)
        .limit(1)
    )


def _org_ok(entity: str | None, orgs: tuple[str, ...]) -> bool:
    scores = [s for s in (org_similarity(entity, o) for o in orgs) if s is not None]
    return bool(scores) and max(scores) >= ORG_MIN


def _best(
    key: str, entity: str | None, tenders: list[Tender], scorer, after: date | None
) -> uuid.UUID | None:
    if not key or is_generic(key):
        return None
    best: tuple[float, uuid.UUID] | None = None
    for t in tenders:
        if after is not None and t.seen_from.date() < after:
            continue
        if not _org_ok(entity, t.orgs):
            continue
        score = max(float(scorer(key, title_key(x))) for x in t.titles)
        if score >= TITLE_MIN and (best is None or score > best[0]):
            best = (score, t.id)
    return best[1] if best else None


def match_award(
    session: Session, award: Award, tenders: list[Tender]
) -> uuid.UUID | None:
    return _by_ref(session, award.tender_ref) or _best(
        title_key(award.title), award.entity, tenders, fuzz.token_sort_ratio, None
    )


def _plan_earliest(plan: ProcurementPlanItem) -> date | None:
    starts = []
    if plan.planned_start is not None:
        starts.append(plan.planned_start)
    if plan.fiscal_year:
        starts.append(date(fiscal_start_year(plan.fiscal_year), 7, 1))
    return min(starts) - PLAN_LEAD if starts else None


def match_plan(
    session: Session, plan: ProcurementPlanItem, tenders: list[Tender]
) -> uuid.UUID | None:
    return _by_ref(session, plan.tender_ref) or _best(
        plan.description_key,
        plan.entity,
        tenders,
        fuzz.token_set_ratio,
        _plan_earliest(plan),
    )


LINK_LOOKBACK = timedelta(days=400)


def link_tender(session: Session, opp: Opportunity, now: datetime) -> int:
    """Link unlinked awards and plan items seen in the last 400 days to this
    tender. Returns how many."""
    if opp.stream != "tender" or opp.visibility != "public":
        return 0
    session.flush()
    tender = _tender_of(opp)
    text = f"{opp.title} {opp.evidence or ''}".lower()
    linked = 0
    for model in (Award, ProcurementPlanItem):
        rows = session.scalars(
            sa.select(model).where(
                model.opportunity_id.is_(None),
                model.last_seen >= now - LINK_LOOKBACK,
                sa.or_(model.entity_key != "", model.tender_ref.is_not(None)),
            )
        ).all()
        for row in rows:
            if _usable_ref(row.tender_ref) and row.tender_ref.lower() in text:
                hit = True
            elif isinstance(row, Award):
                hit = (
                    _best(
                        title_key(row.title),
                        row.entity,
                        [tender],
                        fuzz.token_sort_ratio,
                        None,
                    )
                    is not None
                )
            else:
                hit = (
                    _best(
                        row.description_key,
                        row.entity,
                        [tender],
                        fuzz.token_set_ratio,
                        _plan_earliest(row),
                    )
                    is not None
                )
            if hit:
                row.opportunity_id = opp.id
                linked += 1
    return linked


# --- test-run preview --------------------------------------------------------------


def _money(amount) -> str | None:
    return None if amount is None else f"{amount:.2f}"


def preview(records: Records, now: datetime) -> list[dict[str, Any]]:
    """Each record as it would be stored (snake_case keys), plus what was left
    out. ``None`` entries (no ref and no title; no entity or description) are
    dropped."""
    today = A.today_of(now)
    out: list[dict[str, Any]] = []
    for raw in records.items:
        if records.kind == "award":
            a = A.normalise_award(raw, records.formats, today)
            if a is None:
                continue
            out.append(
                {
                    "kind": "award",
                    "url": a.url,
                    "tender_ref": a.tender_ref,
                    "title": a.title,
                    "entity": a.entity,
                    "winner": a.winner,
                    "amount": _money(a.amount),
                    "currency": a.currency,
                    "awarded_on": a.awarded_on,
                    "period": a.period,
                    "bidders": [
                        {"name": p["bidder"], "price": p["amount"]} for p in a.prices
                    ],
                    "category": a.category,
                    "category_label": categories.label(a.category),
                    "problems": a.problems,
                }
            )
        else:
            p = PL.normalise_plan(raw, records.formats, today)
            if p is None:
                continue
            out.append(
                {
                    "kind": "plan",
                    "url": p.url,
                    "entity": p.entity,
                    "description": p.description,
                    "method": p.method,
                    "estimated_value": _money(p.estimated_amount),
                    "currency": p.currency,
                    "fiscal_year": p.fiscal_year,
                    "planned_quarter": p.planned_quarter,
                    "planned_start": p.planned_start,
                    "planned_end": p.planned_end,
                    "planned_label": period_label(p.planned_start, p.planned_end)
                    if p.planned_start and p.planned_end
                    else None,
                    "category": p.category,
                    "category_label": categories.label(p.category),
                    "problems": p.problems,
                }
            )
    return out
