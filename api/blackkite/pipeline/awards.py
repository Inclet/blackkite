"""Award ingest path (spec 6 ``award``; M5): ``RawAward`` text -> ``award`` rows.

Never writes ``opportunity``. Steps per record:

1. **Normalise** (``normalise_award``, no database): tender ref, title, entity and
   winner cleaned; the winning amount and every bid price with a currency
   (``pipeline/procurement.parse_money``); the award date only with an explicit
   year and not in the future or more than ten years back; category and tags
   from the title (``pipeline/categories``). What was left out is listed in
   ``raw["problems"]``; the listed text is kept in ``raw`` as the supporting text
   of every stored amount and date (spec 10).
2. **Dedupe** on (``ref_key``, ``entity_key``): a re-listed award updates its row
   (values the new listing leaves empty keep the old ones) and ``last_seen``.
3. **Link** to the tender in the catalogue (``pipeline/records.py``): by tender
   ref quoted in the tender's text, else close title and entity.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from blackkite.collectors.base import Formats, RawAward
from blackkite.db.models import Award, Source
from blackkite.pipeline import categories
from blackkite.pipeline import procurement as P
from blackkite.pipeline.dates import kigali_date
from blackkite.pipeline.dedupe import title_key
from blackkite.pipeline.extract import normalise_currency

AWARD_YEARS_BACK = 10


@dataclass
class NormalisedAward:
    ref_key: str
    tender_ref: str | None
    title: str | None
    entity: str | None
    entity_key: str
    winner: str | None
    amount: Decimal | None
    currency: str | None
    awarded_on: date | None
    period: str | None
    bidders: list[dict[str, Any]]
    prices: list[dict[str, Any]]
    category: str
    tags: list[str]
    url: str
    raw: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def money_with_cell(
    text: str | None,
    currency_cell: str | None,
    fmt: Formats,
    problems: P.Problems,
    what: str,
) -> tuple[Decimal | None, str | None]:
    """An amount whose currency may sit in its own cell. A currency cell that
    names no known currency is noted and ignored; one that disagrees with the
    amount's own currency leaves the amount out."""
    cell = P.clean_text(currency_cell, 20)
    code = normalise_currency(cell) if cell else None
    if cell and code is None:
        problems(f"{what}: currency {cell!r} not recognised; ignored")
    amount, currency = P.parse_money(
        text, replace(fmt, currency=code or fmt.currency), problems, what
    )
    if amount is not None and code and currency != code:
        problems(
            f"{what}: {text!r} disagrees with the currency cell {cell!r}; left out"
        )
        return None, None
    return amount, currency


def _money_json(amount: Decimal | None) -> str | None:
    return None if amount is None else f"{amount:.2f}"


def normalise_award(raw: RawAward, fmt: Formats, today: date) -> NormalisedAward | None:
    """None when the record has neither a tender ref nor a title."""
    problems = P.Problems()
    tender_ref = P.clean_ref(raw.tender_ref)
    title = P.clean_text(raw.title, 1000)
    key = P.ref_key(tender_ref)
    if key is None:
        tk = title_key(title)
        if not tk:
            return None
        key = f"title:{tk}"[:300]
    entity = P.clean_entity(raw.entity)
    amount, currency = money_with_cell(
        raw.amount, raw.currency, fmt, problems, "amount"
    )
    awarded_on = P.parse_day(raw.award_date, fmt, problems, "award date")
    if awarded_on is not None and awarded_on > today:
        problems(f"award date: {raw.award_date!r} is in the future; left out")
        awarded_on = None
    elif awarded_on is not None and not P.plausible(
        awarded_on, today, back_years=AWARD_YEARS_BACK, ahead_years=0
    ):
        problems(f"award date: {raw.award_date!r} is implausibly old; left out")
        awarded_on = None
    bidders: list[dict[str, Any]] = []
    prices: list[dict[str, Any]] = []
    for b in raw.bidders:
        name = P.clean_entity(b.name)
        if name:
            bidders.append({"name": name})
        price, cur = money_with_cell(b.price, raw.currency, fmt, problems, "bid price")
        if name or price is not None:
            prices.append(
                {"bidder": name, "amount": _money_json(price), "currency": cur}
            )
    cat = categories.categorise(title)
    listed = {
        k: v
        for k, v in {
            "tender_ref": raw.tender_ref,
            "title": raw.title,
            "entity": raw.entity,
            "winner": raw.winner,
            "amount": raw.amount,
            "currency": raw.currency,
            "award_date": raw.award_date,
            "period": raw.period,
            "bidders": [{"name": b.name, "price": b.price} for b in raw.bidders],
        }.items()
        if v
    }
    return NormalisedAward(
        ref_key=key,
        tender_ref=tender_ref,
        title=title,
        entity=entity,
        entity_key=P.entity_key(entity),
        winner=P.clean_entity(raw.winner),
        amount=amount,
        currency=currency,
        awarded_on=awarded_on,
        period=P.clean_text(raw.period, 100),
        bidders=bidders,
        prices=prices,
        category=cat.category,
        tags=cat.tags,
        url=raw.url,
        raw={"listed": listed, "problems": problems.items},
        problems=problems.items,
    )


UPDATABLE = (
    "tender_ref",
    "title",
    "entity",
    "winner",
    "awarded_on",
    "period",
    "url",
)


def upsert_award(
    session: Session, source: Source, n: NormalisedAward, now: datetime
) -> tuple[Award, bool]:
    """(row, created). Values the new listing leaves empty keep the old ones."""
    row = session.scalar(
        sa.select(Award).where(
            Award.ref_key == n.ref_key, Award.entity_key == n.entity_key
        )
    )
    created = row is None
    if row is None:
        row = Award(
            ref_key=n.ref_key,
            entity_key=n.entity_key,
            first_seen=now,
            source_id=source.id,
        )
        session.add(row)
    for f in UPDATABLE:
        value = getattr(n, f)
        if value is not None or created:
            setattr(row, f, value)
    if n.amount is not None or created:
        row.amount, row.currency = n.amount, n.currency  # amount and currency together
    if n.bidders or created:
        row.bidders = n.bidders
    if n.prices or created:
        row.prices = n.prices
    if n.title is not None or created:
        row.category, row.tags = n.category, n.tags
    row.source_id = row.source_id or source.id
    row.raw = n.raw
    row.last_seen = now
    session.flush()
    return row, created


def today_of(now: datetime) -> date:
    return kigali_date(now)
