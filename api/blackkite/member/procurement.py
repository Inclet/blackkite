"""Benchmarks (awarded prices by category) and coming-up procurement plans
(docs/api-contract.md section 6; spec 2.6, 8).

Both read shared tables only (``award``, ``procurement_plan_item``); nothing per
user is stored. Plans are matched against the caller's own active profiles at
request time (no LLM call). Visibility follows the catalogue rule (spec 4.3,
decision 25): only records from an active or paused source are shown, so a
``testing`` source's awards and plans stay hidden from everyone's screens, as
its opportunities do.

Statistics are robust ones, per (category, currency), never mixing currencies:
median, 25th and 75th percentiles (``percentile_cont``), min, max over awards
with a price above zero, and the median number of bidders over awards that list
bidders. A group needs ``MIN_AWARDS`` (3) priced awards for price statistics
and 3 awards with bidders for ``medianBidders``; with fewer, only the count is
sent. Awards with no stated price or currency form a group with ``currency``
null and counts only.
"""

from __future__ import annotations

import calendar
import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from blackkite.db.models import Award, Opportunity, ProcurementPlanItem, Profile, Source
from blackkite.llm.embeddings import Embedder
from blackkite.member.schemas import CamelModel, OpportunityBenchmark
from blackkite.pipeline import categories
from blackkite.pipeline.dates import kigali_date
from blackkite.pipeline.dedupe import org_key, title_key
from blackkite.pipeline.procurement import period_label
from blackkite.pipeline.visibility import (
    MEMBER_VISIBLE_SOURCE_STATUSES,
    member_visible_public,
)
from blackkite.scoring.match import profile_embedding
from blackkite.scoring.settings import ScoringSettings
from blackkite.scoring.text import TermHit, _str_list, profile_terms, term_hits

MIN_AWARDS = 3
PLAN_WINDOWS = (3, 6, 12)
DEFAULT_PLAN_WINDOW = 12
MAX_PLANS = 200
CENTS = Decimal("0.01")


# --- schemas ---------------------------------------------------------------------


class BenchmarkCategoryOut(CamelModel):
    """One (category, currency) group. Amounts are decimals as strings in
    ``currency``; null when fewer than 3 priced awards (``awards`` still counts
    every award in the group)."""

    category: str
    label: str
    awards: int
    currency: str | None
    median: Decimal | None
    p25: Decimal | None
    p75: Decimal | None
    min: Decimal | None
    max: Decimal | None
    median_bidders: float | None


class BenchmarksOut(CamelModel):
    categories: list[BenchmarkCategoryOut]


class BidderOut(CamelModel):
    omit_if_none = frozenset({"price"})
    name: str | None
    price: Decimal | None = None


class AwardOut(CamelModel):
    omit_if_none = frozenset(
        {
            "tender_ref",
            "entity",
            "title",
            "winner",
            "winning_price",
            "currency",
            "awarded_on",
            "period",
            "url",
            "opportunity_id",
        }
    )
    id: uuid.UUID
    tender_ref: str | None = None
    entity: str | None = None
    title: str | None = None
    winner: str | None = None
    winning_price: Decimal | None = None
    currency: str | None = None
    bidders: list[BidderOut]
    awarded_on: date | None = None
    period: str | None = None
    url: str | None = None
    # The tender in the catalogue, when it is there and the caller may see it.
    opportunity_id: uuid.UUID | None = None


class BenchmarkAwardsOut(CamelModel):
    category: str
    label: str
    total: int
    awards: list[AwardOut]


class PlanOut(CamelModel):
    omit_if_none = frozenset(
        {"method", "estimated_value", "currency", "fiscal_year", "quarter", "url"}
    )
    id: uuid.UUID
    entity: str
    description: str
    category: str
    category_label: str
    method: str | None = None
    estimated_value: Decimal | None = None
    currency: str | None = None
    # When the tender is planned, in the coarsest exact form: "YYYY-MM-DD" (a
    # stated date), "YYYY-MM" (a whole calendar month), "YYYY-Qn" (a whole
    # calendar quarter: a fiscal Q3 of 2026/27 is "2027-Q1"), else
    # "YYYY-MM-DD/YYYY-MM-DD" (start/end). planned_start/planned_end are the
    # same period as dates; planned_label in plain words.
    planned_for: str
    planned_start: date
    planned_end: date
    planned_label: str
    fiscal_year: str | None = None
    quarter: str | None = None
    matched_profile: str
    provisional: bool
    url: str | None = None


class PlansOut(CamelModel):
    window: int  # months
    items: list[PlanOut]


# --- benchmarks ------------------------------------------------------------------


def listed_by_visible_source(model) -> sa.ColumnElement[bool]:
    """An award or plan item is shown while any source that listed it
    (``source_ids``, or the first ``source_id``) is active or paused, so
    retiring one source does not hide a record another still lists."""
    return sa.exists(
        sa.select(sa.literal(1)).where(
            sa.or_(
                Source.id == model.source_id,
                Source.id == sa.any_(model.source_ids),
            ),
            Source.status.in_(MEMBER_VISIBLE_SOURCE_STATUSES),
        )
    )


def _visible_award() -> sa.ColumnElement[bool]:
    return listed_by_visible_source(Award)


def award_filters(
    *,
    category: str | None = None,
    entity: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = None,
) -> list[sa.ColumnElement[bool]]:
    where: list[sa.ColumnElement[bool]] = [_visible_award()]
    if category:
        where.append(Award.category == category)
    if entity:
        key = org_key(entity)
        if key:
            where.append(Award.entity_key.contains(key, autoescape=True))
    if date_from is not None:
        where.append(Award.awarded_on >= date_from)
    if date_to is not None:
        where.append(Award.awarded_on <= date_to)
    if currency:
        where.append(Award.currency == currency)
    return where


def _dec(v: Any) -> Decimal | None:
    if v is None:
        return None
    return Decimal(str(v)).quantize(CENTS, rounding=ROUND_HALF_UP)


def _stats_rows(session: Session, where: list[sa.ColumnElement[bool]]):
    priced = sa.case((Award.amount > 0, Award.amount))
    n_bidders = sa.func.jsonb_array_length(Award.bidders)
    with_bidders = sa.case((n_bidders > 0, n_bidders))

    def pct(p: float, expr):
        return sa.func.percentile_cont(p).within_group(expr)

    return session.execute(
        sa.select(
            Award.category,
            Award.currency,
            sa.func.count(),
            sa.func.count(priced),
            pct(0.5, priced),
            pct(0.25, priced),
            pct(0.75, priced),
            sa.func.min(priced),
            sa.func.max(priced),
            sa.func.count(with_bidders),
            pct(0.5, with_bidders),
        )
        .where(*where)
        .group_by(Award.category, Award.currency)
    ).all()


def _group_out(row) -> BenchmarkCategoryOut:
    (cat, currency, n, n_priced, med, p25, p75, lo, hi, n_bid, med_bid) = row
    stats = currency is not None and n_priced >= MIN_AWARDS
    return BenchmarkCategoryOut(
        category=cat,
        label=categories.label(cat),
        awards=n,
        currency=currency,
        median=_dec(med) if stats else None,
        p25=_dec(p25) if stats else None,
        p75=_dec(p75) if stats else None,
        min=_dec(lo) if stats else None,
        max=_dec(hi) if stats else None,
        median_bidders=float(med_bid)
        if n_bid >= MIN_AWARDS and med_bid is not None and math.isfinite(med_bid)
        else None,
    )


def benchmarks(
    session: Session,
    *,
    category: str | None = None,
    entity: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> BenchmarksOut:
    where = award_filters(
        category=category, entity=entity, date_from=date_from, date_to=date_to
    )
    groups = [_group_out(r) for r in _stats_rows(session, where)]
    order = {k: i for i, k in enumerate(categories.KEYS)}
    groups.sort(
        key=lambda g: (
            order.get(g.category, len(order)),
            g.currency is None,
            -g.awards,
            g.currency or "",
        )
    )
    return BenchmarksOut(categories=groups)


def _bidders_of(a: Award) -> list[BidderOut]:
    if a.prices:
        return [
            BidderOut(
                name=p.get("bidder"),
                price=Decimal(p["amount"]) if p.get("amount") else None,
            )
            for p in a.prices
            if isinstance(p, dict)
        ]
    return [
        BidderOut(name=b.get("name")) for b in a.bidders or [] if isinstance(b, dict)
    ]


def benchmark_awards(
    session: Session,
    category: str,
    *,
    entity: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> BenchmarkAwardsOut:
    where = award_filters(
        category=category,
        entity=entity,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
    )
    total = session.scalar(sa.select(sa.func.count()).select_from(Award).where(*where))
    rows = session.scalars(
        sa.select(Award)
        .where(*where)
        .order_by(
            Award.awarded_on.desc().nulls_last(), Award.created_at.desc(), Award.id
        )
        .limit(limit)
        .offset(offset)
    ).all()
    linked = {a.opportunity_id for a in rows if a.opportunity_id}
    visible = (
        set(
            session.scalars(
                sa.select(Opportunity.id).where(
                    Opportunity.id.in_(linked), member_visible_public()
                )
            )
        )
        if linked
        else set()
    )
    return BenchmarkAwardsOut(
        category=category,
        label=categories.label(category),
        total=total or 0,
        awards=[
            AwardOut(
                id=a.id,
                tender_ref=a.tender_ref,
                entity=a.entity,
                title=a.title,
                winner=a.winner,
                winning_price=a.amount,
                currency=a.currency,
                bidders=_bidders_of(a),
                awarded_on=a.awarded_on,
                period=a.period,
                url=a.url,
                opportunity_id=a.opportunity_id
                if a.opportunity_id in visible
                else None,
            )
            for a in rows
        ],
    )


def opportunity_benchmark(
    session: Session, opp: Opportunity
) -> OpportunityBenchmark | None:
    """The tender's category prices, when it has ≥ 3 priced awards in one
    currency: the tender's own currency if it states one and that group has
    enough, else the currency with the most priced awards."""
    if opp.stream != "tender":
        return None
    cat = categories.opportunity_category(opp)
    if cat == categories.OTHER:
        return None
    groups = [
        g
        for g in (
            _group_out(r) for r in _stats_rows(session, award_filters(category=cat))
        )
        if g.median is not None
    ]
    if not groups:
        return None
    own = [g for g in groups if g.currency == opp.value_currency]
    g = (own or sorted(groups, key=lambda g: (-g.awards, g.currency or "")))[0]
    return OpportunityBenchmark(
        category=g.category,
        label=g.label,
        awards=g.awards,
        currency=g.currency or "",
        median=g.median,
        p25=g.p25,
        p75=g.p75,
        min=g.min,
        max=g.max,
    )


# --- plans -----------------------------------------------------------------------


def _months_ahead(d: date, months: int) -> date:
    m = d.month - 1 + months
    year, month = d.year + m // 12, m % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def planned_for(start: date, end: date) -> str:
    """The planned period as "YYYY-MM-DD", "YYYY-MM", "YYYY-Qn" or
    "start/end" (ISO dates)."""
    if start == end:
        return start.isoformat()
    last = calendar.monthrange(end.year, end.month)[1]
    if start.day == 1 and end.day == last and start.year == end.year:
        if start.month == end.month:
            return f"{start:%Y-%m}"
        if end.month - start.month == 2 and start.month % 3 == 1:
            return f"{start.year}-Q{(start.month - 1) // 3 + 1}"
    return f"{start.isoformat()}/{end.isoformat()}"


def _follows_tenders(profile: Profile) -> bool:
    streams = (profile.data or {}).get("streams")
    return not (isinstance(streams, list) and streams) or "tender" in streams


def _excluded(plan: ProcurementPlanItem, profile: Profile) -> bool:
    ex = (profile.data or {}).get("exclusions")
    if not isinstance(ex, dict):
        return False
    entity = plan.entity.lower()
    if any(o.lower() in entity for o in _str_list(ex.get("organisations"))):
        return True
    text = plan.description.lower()
    if any(k.lower() in text for k in _str_list(ex.get("keywords"))):
        return True
    sectors = {t.split(":", 1)[-1] for t in plan.tags or []}
    return any(s.lower() in sectors for s in _str_list(ex.get("sectors")))


def _below_min(plan: ProcurementPlanItem, profile: Profile) -> bool:
    raw = (profile.data or {}).get("min_contract_rwf")
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return False
    return (
        plan.currency == "RWF"
        and plan.estimated_amount is not None
        and plan.estimated_amount < Decimal(str(raw))
    )


def _cosine(a: Any, b: Any) -> float | None:
    try:
        a, b = [float(x) for x in a], [float(x) for x in b]
    except TypeError:
        return None
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if not na or not nb or len(a) != len(b):
        return None
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)


def _plan_text(plan: ProcurementPlanItem) -> str:
    labels = [t.split(":", 1)[-1].replace("_", " ") for t in plan.tags or []]
    return "\n".join([plan.description, *labels])


SERVICE_FIELDS = ("services", "sectors")


def service_categories(profile: Profile) -> set[str]:
    """Benchmark categories the profile's services and sectors name, each
    service counted only when it names exactly one ("dry freight": transport;
    "digital consulting" names consultancy and IT, so neither)."""
    out: set[str] = set()
    data = profile.data or {}
    for f in SERVICE_FIELDS:
        for term in _str_list(data.get(f)):
            cat = categories.categorise(term)
            if cat.category != categories.OTHER and len(cat.tags) == 1:
                out.add(cat.category)
    return out


def _category_words(key: str) -> set[str]:
    """The plan category's key and the words of its label ("Agriculture";
    "Food and catering": food, catering)."""
    if key == categories.OTHER:
        return set()
    words = set(title_key(categories.label(key)).split()) - {"and"}
    return words | {key}


def _service_match(
    hit: TermHit, *, category: bool, category_words: set[str], shared: int
) -> bool:
    """A whole profile term in the plan: a phrase of two or more words (word for
    word or through the synonyms), or a one-word term word for word (never a
    one-word synonym: "software" does not match "solar system"). A one-word term
    ("health") is too broad alone: it counts only with category agreement (the
    plan's category is one the profile's services name, or the term names the
    plan's category: "agriculture" for an agriculture plan), or a second distinct
    word shared with the profile's terms ("Construction of a health centre" is
    not a health NGO's service)."""
    if not hit.phrase:
        return False
    if len(hit.stems) > 1:
        return True
    agrees = category or title_key(hit.term) in category_words
    return hit.literal and (agrees or shared >= MIN_SHARED_TOKENS)


@dataclass(frozen=True)
class PlanMatch:
    services: int  # whole profile terms found
    tokens: int  # distinct plan words shared with the profile's terms
    category: bool
    similarity: float | None

    @property
    def rank(self) -> tuple[int, int, int, float]:
        return (self.services, int(self.category), self.tokens, self.similarity or 0.0)


MIN_SHARED_TOKENS = 2


def plan_match(
    plan: ProcurementPlanItem,
    terms: list[str],
    cats: set[str],
    similarity: float | None,
    settings: ScoringSettings,
) -> PlanMatch | None:
    """A plan matches a profile on any of: a whole service (or sector) phrase
    (a one-word term only with the category or a second shared word, see
    ``_service_match``); at least two distinct shared words; its category being one the profile's
    services name; embedding similarity at the threshold. One shared word alone
    ("dry" foodstuffs, "health" centre construction) is too weak."""
    hits = term_hits(terms, _plan_text(plan))
    shared = len(frozenset().union(*(h.stems for h in hits))) if hits else 0
    category = plan.category != categories.OTHER and plan.category in cats
    words = _category_words(plan.category)
    services = sum(
        1
        for h in hits
        if _service_match(h, category=category, category_words=words, shared=shared)
    )
    similar = similarity is not None and similarity >= settings.embedding_min_similarity
    if services or shared >= MIN_SHARED_TOKENS or category or similar:
        return PlanMatch(services, shared, category, similarity)
    return None


def plans_for(
    session: Session,
    user_id: uuid.UUID,
    *,
    now: datetime,
    window: int = DEFAULT_PLAN_WINDOW,
    profile_id: uuid.UUID | None = None,
    settings: ScoringSettings,
    embedder: Embedder | None = None,
) -> PlansOut | None:
    """Plans matching the caller's active profiles. None when ``profile_id`` is
    not one of the caller's active profiles."""
    q = sa.select(Profile).where(Profile.user_id == user_id, Profile.active.is_(True))
    if profile_id is not None:
        q = q.where(Profile.id == profile_id)
    profiles = list(session.scalars(q.order_by(Profile.created_at, Profile.name)))
    if profile_id is not None and not profiles:
        return None
    profiles = [p for p in profiles if _follows_tenders(p)]
    if not profiles:
        return PlansOut(window=window, items=[])
    today = kigali_date(now)
    until = _months_ahead(today, window)
    advertised = sa.exists(
        sa.select(sa.literal(1)).where(
            Opportunity.id == ProcurementPlanItem.opportunity_id,
            member_visible_public(),
        )
    )
    plans = session.scalars(
        sa.select(ProcurementPlanItem)
        .where(
            ProcurementPlanItem.planned_start.is_not(None),
            ProcurementPlanItem.planned_end >= today,
            ProcurementPlanItem.planned_start <= until,
            sa.not_(advertised),
            listed_by_visible_source(ProcurementPlanItem),
        )
        .order_by(
            ProcurementPlanItem.planned_start,
            ProcurementPlanItem.entity,
            ProcurementPlanItem.description,
        )
    ).all()
    if embedder is not None and any(p.embedding is not None for p in plans):
        vectors = {p.id: profile_embedding(p, embedder) for p in profiles}
    else:
        vectors = {}
    terms = {p.id: profile_terms(p) for p in profiles}
    cats = {p.id: service_categories(p) for p in profiles}
    out: list[PlanOut] = []
    for plan in plans:
        best: tuple[tuple, int, Profile] | None = None
        for i, prof in enumerate(profiles):
            if _excluded(plan, prof) or _below_min(plan, prof):
                continue
            sim = None
            if plan.embedding is not None and vectors.get(prof.id) is not None:
                sim = _cosine(plan.embedding, vectors[prof.id])
            m = plan_match(plan, terms[prof.id], cats[prof.id], sim, settings)
            if m is None:
                continue
            if best is None or (m.rank, -i) > (best[0], -best[1]):
                best = (m.rank, i, prof)
        if best is None:
            continue
        prof = best[2]
        out.append(
            PlanOut(
                id=plan.id,
                entity=plan.entity,
                description=plan.description,
                category=plan.category,
                category_label=categories.label(plan.category),
                method=plan.method,
                estimated_value=plan.estimated_amount,
                currency=plan.currency,
                planned_for=planned_for(plan.planned_start, plan.planned_end),
                planned_start=plan.planned_start,
                planned_end=plan.planned_end,
                planned_label=period_label(plan.planned_start, plan.planned_end),
                fiscal_year=plan.fiscal_year,
                quarter=plan.planned_quarter,
                matched_profile=prof.name,
                provisional=bool((prof.data or {}).get("provisional")),
                url=plan.url,
            )
        )
        if len(out) >= MAX_PLANS:
            break
    return PlansOut(window=window, items=out)
