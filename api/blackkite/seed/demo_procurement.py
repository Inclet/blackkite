"""FICTIONAL awards and procurement plan items for ``bk demo-seed`` (dev only), so
the benchmarks and "coming up" screens can be exercised before Umucyo is
collected.

Everything is made up: entities and companies carry "(fictional)", tender refs
start with "DEMO/", links are on demo.example.com, and every row has
``raw["_demo"] = true`` (how a re-run finds and replaces them). Prices are
invented round-ish numbers, not taken from any real award. Rows hang on the demo
issuer source, so they are visible like the demo catalogue.

25 awards across four categories (transport, IT, construction, office supplies),
dated in the past year; 10 plan items planned over the next twelve months, one of
them linked to the demo dry-freight tender (so it is left out of the plans list,
as an advertised tender is).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from blackkite.db.models import Award, Opportunity, ProcurementPlanItem, Source
from blackkite.pipeline import categories
from blackkite.pipeline.dates import kigali_date
from blackkite.pipeline.procurement import (
    description_key,
    entity_key,
    fiscal_year_of,
    ref_key,
)

DEMO = {"_demo": True}
HOST = "https://demo.example.com/procurement"

ENTITIES = (
    "Example Grain Board (fictional)",
    "Example Ministry of Data (fictional)",
    "Example District Council (fictional)",
    "Example Health Supplies Agency (fictional)",
)
COMPANIES = (
    "Example Haulage Ltd (fictional)",
    "Example Movers (fictional)",
    "Example Freight Partners (fictional)",
    "Example Code Works (fictional)",
    "Example Systems Ltd (fictional)",
    "Example Builders (fictional)",
    "Example Civil Works Co (fictional)",
    "Example Office Supply (fictional)",
    "Example Furniture House (fictional)",
)

# (title, entity index, winning price in RWF, number of bidders, days ago)
AWARDS: tuple[tuple[str, int, int, int, int], ...] = (
    ("[Demo] Transport of maize to district stores", 0, 6_100_000, 4, 20),
    ("[Demo] Transport of fertiliser to cooperatives", 0, 4_200_000, 3, 45),
    ("[Demo] Haulage of bagged grain, northern route", 0, 9_800_000, 5, 70),
    ("[Demo] Refrigerated transport of vaccines", 3, 12_500_000, 2, 95),
    ("[Demo] Courier services for medical samples", 3, 2_300_000, 6, 120),
    ("[Demo] Transport of school materials", 2, 5_400_000, 4, 150),
    ("[Demo] Cold chain transport framework", 3, 15_000_000, 3, 200),
    ("[Demo] Supply of laptops and desktop computers", 1, 18_000_000, 7, 30),
    ("[Demo] Development of a case management software", 1, 32_000_000, 4, 60),
    ("[Demo] Maintenance of the data centre network", 1, 8_500_000, 3, 90),
    ("[Demo] Website redesign and hosting", 2, 3_900_000, 9, 130),
    ("[Demo] Supply of servers", 1, 24_000_000, 2, 170),
    ("[Demo] Digital records management system", 3, 27_500_000, 5, 240),
    ("[Demo] Construction of a classroom block", 2, 85_000_000, 6, 40),
    ("[Demo] Rehabilitation of a feeder road", 2, 140_000_000, 4, 80),
    ("[Demo] Renovation of office buildings", 1, 38_000_000, 5, 110),
    ("[Demo] Construction of a grain store", 0, 210_000_000, 3, 160),
    ("[Demo] Plumbing works at a health centre", 3, 7_200_000, 8, 210),
    ("[Demo] Painting of the district hall", 2, 4_800_000, 6, 300),
    ("[Demo] Supply of office stationery", 1, 2_100_000, 5, 25),
    ("[Demo] Supply of office furniture", 2, 6_700_000, 4, 75),
    ("[Demo] Printing of annual reports", 0, 1_800_000, 6, 100),
    ("[Demo] Supply of toners and paper", 3, 1_200_000, 7, 140),
    ("[Demo] Supply of furniture for a training centre", 0, 9_300_000, 3, 190),
    ("[Demo] Office supplies framework", 2, 3_300_000, 4, 280),
)

# (description, entity index, estimated RWF or None, months ahead, method)
PLANS: tuple[tuple[str, int, int | None, int, str], ...] = (
    (
        "[Demo] Transport of bagged grain to regional stores",
        0,
        40_000_000,
        2,
        "Open competitive bidding",
    ),
    (
        "[Demo] Refrigerated distribution of vaccines to health centres",
        3,
        55_000_000,
        4,
        "Open competitive bidding",
    ),
    (
        "[Demo] Last-mile delivery of school feeding supplies",
        2,
        12_000_000,
        7,
        "Restricted tendering",
    ),
    (
        "[Demo] Development of a stock management information system",
        0,
        30_000_000,
        3,
        "Open competitive bidding",
    ),
    (
        "[Demo] Data analytics consultancy for health records",
        3,
        None,
        9,
        "Quality and cost based selection",
    ),
    (
        "[Demo] Supply of office furniture",
        1,
        6_000_000,
        5,
        "Request for quotations",
    ),
    (
        "[Demo] Construction of a market shed",
        2,
        120_000_000,
        8,
        "Open competitive bidding",
    ),
    (
        "[Demo] Transport of fertiliser for the next season",
        0,
        3_000_000,
        10,
        "Request for quotations",
    ),
    (
        "[Demo] Catering services for training sessions",
        1,
        2_500_000,
        6,
        "Request for quotations",
    ),
    # Linked below to the demo dry-freight tender: left out of the plans list.
    (
        "[Demo] Dry freight and last-mile distribution framework",
        0,
        None,
        1,
        "Open competitive bidding",
    ),
)
LINKED_PLAN_TITLE = "[Demo] Dry freight and last-mile distribution framework"


def _quarter(d: date) -> tuple[date, date, str]:
    """The calendar quarter holding ``d`` and its fiscal quarter label (Rwanda's
    fiscal year starts in July)."""
    q = (d.month - 1) // 3
    start = date(d.year, 3 * q + 1, 1)
    end_month = start.month + 2
    nxt = date(d.year + (end_month == 12), end_month % 12 + 1, 1)
    fiscal_q = (q + 2) % 4 + 1
    return start, nxt - timedelta(days=1), f"Q{fiscal_q}"


def _months_ahead(d: date, months: int) -> date:
    m = d.month - 1 + months
    return date(d.year + m // 12, m % 12 + 1, 15)


def _demo_rows():
    return sa.cast(Award.raw["_demo"], sa.Boolean).is_(True)


def clear(db: Session) -> tuple[int, int]:
    awards = db.execute(sa.delete(Award).where(_demo_rows())).rowcount
    plans = db.execute(
        sa.delete(ProcurementPlanItem).where(
            sa.cast(ProcurementPlanItem.raw["_demo"], sa.Boolean).is_(True)
        )
    ).rowcount
    return awards, plans


def seed(db: Session, source: Source, now: datetime) -> tuple[int, int]:
    """Replace the demo awards and plans; returns (awards, plans)."""
    clear(db)
    today = kigali_date(now)
    for i, (title, e, price, n_bidders, days_ago) in enumerate(AWARDS, start=1):
        entity = ENTITIES[e]
        cat = categories.categorise(title)
        bidders = [COMPANIES[(i + k) % len(COMPANIES)] for k in range(n_bidders)]
        prices = [
            {
                "bidder": b,
                "amount": f"{Decimal(price) * (1 + Decimal(k) / 10):.2f}",
                "currency": "RWF",
            }
            for k, b in enumerate(bidders)
        ]
        ref = f"DEMO/{i:03d}/{today.year}"
        db.add(
            Award(
                tender_ref=ref,
                ref_key=ref_key(ref),
                title=title,
                entity=entity,
                entity_key=entity_key(entity),
                winner=bidders[0],
                bidders=[{"name": b} for b in bidders],
                prices=prices,
                amount=Decimal(price),
                currency="RWF",
                awarded_on=today - timedelta(days=days_ago),
                period="12 months (fictional)",
                category=cat.category,
                tags=cat.tags,
                url=f"{HOST}/awards/{i}",
                source_id=source.id,
                raw=dict(DEMO),
                first_seen=now,
                last_seen=now,
            )
        )
    linked = db.scalar(
        sa.select(Opportunity.id).where(
            Opportunity.title == LINKED_PLAN_TITLE,
            Opportunity.evidence["_demo"].as_boolean().is_(True),
        )
    )
    for i, (description, e, estimate, months, method) in enumerate(PLANS, start=1):
        entity = ENTITIES[e]
        cat = categories.categorise(description)
        start, end, fiscal_q = _quarter(_months_ahead(today, months))
        db.add(
            ProcurementPlanItem(
                entity=entity,
                entity_key=entity_key(entity),
                description=description,
                description_key=description_key(description),
                category=cat.category,
                tags=cat.tags,
                method=method,
                estimated_amount=Decimal(estimate) if estimate else None,
                currency="RWF" if estimate else None,
                fiscal_year=fiscal_year_of(start),
                planned_quarter=fiscal_q,
                planned_start=start,
                planned_end=end,
                url=f"{HOST}/plans/{i}",
                opportunity_id=linked if description == LINKED_PLAN_TITLE else None,
                source_id=source.id,
                raw=dict(DEMO),
                first_seen=now,
                last_seen=now,
            )
        )
    db.flush()
    return len(AWARDS), len(PLANS)
