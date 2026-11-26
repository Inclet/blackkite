"""Procurement plan ingest path (spec 2.6; M5): ``RawPlan`` text ->
``procurement_plan_item`` rows. Never writes ``opportunity``.

1. **Normalise** (``normalise_plan``, no database): entity and description
   cleaned; estimated value with a currency; fiscal year ("2026/27"); the planned
   period from a stated date, or from a quarter with the source's stated basis
   and an explicit fiscal or calendar year (never guessed; otherwise the item
   is kept with no planned period, and the plans API leaves it out of its
   windows); category and tags from the description.
2. **Dedupe** on (entity, description, fiscal year), normalised keys.
3. **Embed** (optional): when an embedder is configured, the description is
   embedded for the cheap profile match. No key, no embedding; nothing fails.
4. **Link** to the advertised tender once it is in the catalogue
   (``pipeline/records.py``; also run on every tender ingest).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from blackkite.collectors.base import Formats, RawPlan
from blackkite.db.models import ProcurementPlanItem, Source
from blackkite.llm.embeddings import Embedder, EmbeddingError
from blackkite.pipeline import categories
from blackkite.pipeline import procurement as P
from blackkite.pipeline.awards import add_source_id, money_with_cell

log = logging.getLogger("blackkite.pipeline")

PLAN_YEARS_BACK = 2
PLAN_YEARS_AHEAD = 3


@dataclass
class NormalisedPlan:
    entity: str
    entity_key: str
    description: str
    description_key: str
    method: str | None
    estimated_amount: Decimal | None
    currency: str | None
    fiscal_year: str | None
    planned_quarter: str | None
    planned_date: date | None
    planned_start: date | None
    planned_end: date | None
    tender_ref: str | None
    category: str
    tags: list[str]
    url: str
    raw: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def normalise_plan(raw: RawPlan, fmt: Formats, today: date) -> NormalisedPlan | None:
    """None when the entry has no entity or no description."""
    problems = P.Problems()
    entity = P.clean_entity(raw.entity)
    description = P.clean_text(raw.description, 2000)
    if not entity or not description:
        return None
    fiscal_year = P.parse_fiscal_year(raw.fiscal_year)
    if raw.fiscal_year and fiscal_year is None:
        problems(f"fiscal year: {raw.fiscal_year!r} not understood; left out")
    quarter, quarter_year = P.parse_quarter(raw.planned_quarter)
    if raw.planned_quarter and quarter is None:
        problems(f"quarter: {raw.planned_quarter!r} not understood; left out")
    if quarter and fiscal_year is None:
        fiscal_year = P.parse_fiscal_year(raw.planned_quarter)
    planned_date = P.parse_day(raw.planned_date, fmt, problems, "planned date")
    start = end = None
    if planned_date is not None:
        start = end = planned_date
    elif quarter:
        period = P.quarter_period(
            quarter,
            basis=fmt.quarter_basis,
            fiscal_year=fiscal_year,
            calendar_year=quarter_year,
        )
        if period is None:
            problems(
                f"quarter: {quarter} has no stated year for its basis "
                f"({fmt.quarter_basis or 'none'}); no planned dates"
            )
        else:
            start, end = period
    if start is not None and not (
        P.plausible(
            start, today, back_years=PLAN_YEARS_BACK, ahead_years=PLAN_YEARS_AHEAD
        )
        and P.plausible(
            end, today, back_years=PLAN_YEARS_BACK, ahead_years=PLAN_YEARS_AHEAD
        )
    ):
        problems(f"planned period {start} to {end} is implausible; left out")
        start = end = None
        planned_date = None
    amount, currency = money_with_cell(
        raw.estimated_value, raw.currency, fmt, problems, "estimated value"
    )
    cat = categories.categorise(description)
    listed = {
        k: v
        for k, v in {
            "entity": raw.entity,
            "description": raw.description,
            "method": raw.method,
            "estimated_value": raw.estimated_value,
            "currency": raw.currency,
            "planned_date": raw.planned_date,
            "planned_quarter": raw.planned_quarter,
            "fiscal_year": raw.fiscal_year,
            "tender_ref": raw.tender_ref,
        }.items()
        if v
    }
    return NormalisedPlan(
        entity=entity,
        entity_key=P.entity_key(entity),
        description=description,
        description_key=P.description_key(description),
        method=P.clean_text(raw.method, 200),
        estimated_amount=amount,
        currency=currency,
        fiscal_year=fiscal_year,
        planned_quarter=quarter,
        planned_date=planned_date,
        planned_start=start,
        planned_end=end,
        tender_ref=P.clean_ref(raw.tender_ref),
        category=cat.category,
        tags=cat.tags,
        url=raw.url,
        raw={"listed": listed, "problems": problems.items},
        problems=problems.items,
    )


FIELDS = (
    "entity",
    "description",
    "method",
    "fiscal_year",
    "planned_quarter",
    "planned_date",
    "tender_ref",
    "url",
    "category",
)


def embedding_text(plan: ProcurementPlanItem) -> str:
    labels = [t.split(":", 1)[-1] for t in plan.tags or []]
    parts = [plan.description, f"Procuring entity: {plan.entity}"]
    if labels:
        parts.append("Tags: " + ", ".join(labels))
    return "\n".join(parts)


def find_plan(session: Session, n: NormalisedPlan) -> ProcurementPlanItem | None:
    """The stored plan item this listing is, merging what a listing left out:

    1. same (entity, description, fiscal year);
    2. the listing states a fiscal year and the same entity and description is
       stored without one: that row (it takes the year);
    3. the listing states no fiscal year and exactly one row has the same entity
       and description: that row;
    4. the listing has a tender ref and exactly one row of the same entity has
       that ref, with the same or no fiscal year: that row.
    """
    same = sa.and_(
        ProcurementPlanItem.entity_key == n.entity_key,
        ProcurementPlanItem.description_key == n.description_key,
    )
    row = session.scalar(
        sa.select(ProcurementPlanItem).where(
            same, ProcurementPlanItem.fiscal_year.is_not_distinct_from(n.fiscal_year)
        )
    )
    if row is not None:
        return row
    if n.fiscal_year is not None:
        row = session.scalar(
            sa.select(ProcurementPlanItem).where(
                same, ProcurementPlanItem.fiscal_year.is_(None)
            )
        )
        if row is not None:
            return row
    else:
        rows = session.scalars(sa.select(ProcurementPlanItem).where(same)).all()
        if len(rows) == 1:
            return rows[0]
    if n.tender_ref:
        q = sa.select(ProcurementPlanItem).where(
            ProcurementPlanItem.entity_key == n.entity_key,
            sa.func.lower(ProcurementPlanItem.tender_ref) == n.tender_ref.lower(),
        )
        if n.fiscal_year is not None:
            q = q.where(
                sa.or_(
                    ProcurementPlanItem.fiscal_year.is_(None),
                    ProcurementPlanItem.fiscal_year == n.fiscal_year,
                )
            )
        rows = session.scalars(q).all()
        if len(rows) == 1:
            return rows[0]
    return None


def upsert_plan(
    session: Session,
    source: Source,
    n: NormalisedPlan,
    now: datetime,
    *,
    embedder: Embedder | None = None,
) -> tuple[ProcurementPlanItem, bool]:
    row = find_plan(session, n)
    created = row is None
    if row is None:
        row = ProcurementPlanItem(
            entity_key=n.entity_key,
            description_key=n.description_key,
            first_seen=now,
            source_id=source.id,
        )
        session.add(row)
    changed_text = created or row.description != n.description
    for f in FIELDS:
        value = getattr(n, f)
        if value is not None or created:
            setattr(row, f, value)
    row.tags = n.tags
    if n.planned_start is not None or created:
        row.planned_start, row.planned_end = n.planned_start, n.planned_end
    if n.estimated_amount is not None or created:
        row.estimated_amount, row.currency = n.estimated_amount, n.currency
    row.source_id = row.source_id or source.id
    row.source_ids = add_source_id(row.source_ids, row.source_id, source.id)
    row.raw = n.raw
    row.last_seen = now
    if embedder is not None and (changed_text or row.embedding is None):
        try:
            [row.embedding] = embedder.embed([embedding_text(row)])
        except (EmbeddingError, ValueError) as exc:
            log.warning("plan embedding failed: %s", exc)
    session.flush()
    return row, created
