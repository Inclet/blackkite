"""`bk demo-seed`: a small, fictional catalogue for a local look at the feed and a
dry-run digest before real sources exist. Dev databases only.

Everything here is made up: the organisations are invented ("(fictional)" in the
name), every title starts with "[Demo]", every URL is on example.com, and no real
notice is copied. Each demo opportunity carries ``evidence._demo = true`` and is
linked to one of the two demo sources below; that is how a re-run finds and
replaces them, and how the "no non-demo opportunities" guard tells them apart.

The demo sources are ``active`` so members see their items, but they cannot be
collected: collector type ``custom`` with no class (a forced run fails cleanly
with "not implemented", no network) and a once-a-year schedule. Two succeeded
``source_run`` rows give them an "ok" health on the sources page.

Scoring is rules-only (no model, no embedder, no API keys): tenders and funding
get at most a "possible" fit word, as any rules-only score does (scoring/service.py).

This is NOT the Phase 4 exit check, which needs real collected data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from blackkite.db.models import (
    Opportunity,
    OpportunitySource,
    Profile,
    Source,
    SourceRun,
)
from blackkite.pipeline.dates import KIGALI
from blackkite.pipeline.validate import status_for, trust_state, verification_for
from blackkite.scoring import service as scoring
from blackkite.scoring.backfill import clear_requests
from blackkite.scoring.settings import get_scoring_settings
from blackkite.seed.loader import bootstrap

DEMO_MARK = "_demo"
DEMO_HOST = "https://demo.example.com"
# A schedule that fires once a year (1 January, 00:00 UTC): the demo sources are
# never collected in practice, and a forced run fails without a request.
DEMO_SCHEDULE = "0 0 1 1 *"
ACCESS_NOTE = (
    "Fictional demo source created by `bk demo-seed`. Not a real site; never "
    "collected. Delete the demo data by resetting the dev database."
)

DEMO_SOURCES: dict[str, dict[str, Any]] = {
    "issuer": {
        "name": "Demo issuer portal (fictional)",
        "home_url": f"{DEMO_HOST}/issuer/",
        "publisher": "Demo Issuer Portal",
        "kind": "original",
    },
    "board": {
        "name": "Demo notice board (fictional)",
        "home_url": f"{DEMO_HOST}/board/",
        "publisher": "Demo Notice Board",
        "kind": "publisher",
    },
}


@dataclass(frozen=True)
class DemoItem:
    slug: str
    stream: str
    title: str
    organisation: str
    summary: str
    source: str  # key of DEMO_SOURCES
    days: int  # deadline (or event start) in days from today, Kigali
    organisation_short: str | None = None
    subtype: str | None = None
    tags: tuple[str, ...] = ()
    value: tuple[int, str] | None = None
    value_note: str | None = None
    location: str | None = "Kigali, Rwanda"
    eligibility: str | None = None
    requirements: tuple[str, ...] = ()
    event_days: int = 0  # extra days an event lasts
    extra: dict[str, Any] = field(default_factory=dict)


DEMO_ITEMS: tuple[DemoItem, ...] = (
    DemoItem(
        "cold-chain-vaccines",
        "tender",
        "[Demo] Cold chain transport of vaccines to district hospitals",
        "Example Health Supplies Agency (fictional)",
        "A fictional call for refrigerated transport from a central store to "
        "district hospitals. Demo data only.",
        "issuer",
        12,
        organisation_short="EHSA (fictional)",
        subtype="request for bids",
        tags=("service:cold chain transport", "sector:health"),
        value=(45_000_000, "RWF"),
        requirements=("Refrigerated trucks able to hold 2 to 8 degrees Celsius.",),
    ),
    DemoItem(
        "dry-freight-framework",
        "tender",
        "[Demo] Dry freight and last-mile distribution framework",
        "Example Grain Board (fictional)",
        "A fictional framework for moving bagged grain by road and delivering it "
        "to rural stores. Demo data only.",
        "board",
        4,
        subtype="framework agreement",
        tags=(
            "service:dry freight",
            "service:last-mile distribution",
            "sector:agriculture",
        ),
        requirements=(
            "Copies of vehicle logbooks for every truck proposed.",
            "Three similar contracts completed in the last five years.",
        ),
    ),
    DemoItem(
        "data-platform",
        "tender",
        "[Demo] Design and build of a public data platform",
        "Example Ministry of Data (fictional)",
        "A fictional request for a team to build a data platform and its "
        "dashboards. Demo data only.",
        "issuer",
        20,
        subtype="request for proposals",
        tags=("service:software development", "service:data", "sector:public sector"),
        value=(120_000_000, "RWF"),
    ),
    DemoItem(
        "office-cleaning",
        "tender",
        "[Demo] Office cleaning services for a head office",
        "Example Hotel Group (fictional)",
        "A fictional cleaning contract, here to show an item that matches no "
        "profile. Demo data only.",
        "board",
        9,
        tags=("service:cleaning", "sector:hospitality"),
        value=(8_000_000, "RWF"),
    ),
    DemoItem(
        "agri-logistics-grant",
        "funding",
        "[Demo] Agri-logistics innovation grant",
        "Example Rural Foundation (fictional)",
        "A fictional grant for companies improving how farm produce reaches "
        "markets. Demo data only.",
        "issuer",
        30,
        subtype="grant",
        tags=("service:last-mile distribution", "sector:agriculture"),
        value=(50_000, "USD"),
        eligibility="Registered companies operating in Rwanda.",
    ),
    DemoItem(
        "ai-public-services",
        "funding",
        "[Demo] AI for public services challenge",
        "Example Innovation Fund (fictional)",
        "A fictional competition for AI tools that help public services. Demo "
        "data only.",
        "board",
        40,
        subtype="competition",
        tags=("service:AI/ML", "sector:public sector"),
        value=(20_000, "USD"),
    ),
    DemoItem(
        "treasury-bond",
        "investment",
        "[Demo] Five-year treasury bond, fictional issue",
        "Example Central Bank (fictional)",
        "A fictional bond issue with a fictional coupon. Facts only, no "
        "recommendation. Demo data only.",
        "issuer",
        6,
        subtype="treasury bond",
        tags=("sector:treasury bonds",),
        value_note="fictional coupon, demo only",
        location="Rwanda",
    ),
    DemoItem(
        "corporate-bond",
        "investment",
        "[Demo] Corporate bond offer, fictional issuer",
        "Example Power Company (fictional)",
        "A fictional corporate bond offer open to retail investors. Facts only, "
        "no recommendation. Demo data only.",
        "board",
        15,
        subtype="corporate bond",
        tags=("sector:corporate bonds",),
        value_note="fictional minimum subscription",
        location="Rwanda",
    ),
    DemoItem(
        "logistics-meetup",
        "event",
        "[Demo] Logistics and trade meetup",
        "Example Traders Network (fictional)",
        "A fictional evening meetup for people in logistics and trade. Demo data only.",
        "issuer",
        10,
        tags=("sector:logistics and trade",),
        location="Example Hall, Kigali (fictional)",
    ),
    DemoItem(
        "fintech-summit",
        "event",
        "[Demo] Fintech and startups summit",
        "Example Summit Organisers (fictional)",
        "A fictional two-day summit on finance, fintech and startups. Demo data only.",
        "board",
        3,
        tags=("sector:finance and fintech", "sector:startups and investors"),
        location="Example Convention Centre, Kigali (fictional)",
        event_days=1,
    ),
)


class DemoRefused(Exception):
    """The demo seed will not run here; the message says why."""


@dataclass
class DemoResult:
    items: int
    sources: int
    replaced: int
    stats: scoring.RunStats
    admin_email: str


def _demo_filter() -> sa.ColumnElement[bool]:
    return Opportunity.evidence[DEMO_MARK].as_boolean().is_(True)


def non_demo_count(db: Session) -> int:
    return db.scalar(
        sa.select(sa.func.count())
        .select_from(Opportunity)
        .where(sa.not_(sa.func.coalesce(_demo_filter(), False)))
    )


def _at(today, days: int, hour: int) -> datetime:
    return datetime.combine(today + timedelta(days=days), time(hour), KIGALI)


def _source(db: Session, spec: dict[str, Any], now: datetime) -> Source:
    s = db.scalar(sa.select(Source).where(Source.name == spec["name"]))
    if s is None:
        s = Source(name=spec["name"])
        db.add(s)
    s.home_url = spec["home_url"]
    s.publisher = spec["publisher"]
    s.kind = spec["kind"]
    s.streams = ["tender", "investment", "funding", "event"]
    s.collector_type = "custom"
    s.config = {}
    s.schedule = DEMO_SCHEDULE
    s.access_note = ACCESS_NOTE
    s.status = "active"
    db.flush()
    db.execute(sa.delete(SourceRun).where(SourceRun.source_id == s.id))
    for hours in (30, 6):
        db.add(
            SourceRun(
                source_id=s.id,
                status="succeeded",
                started_at=now - timedelta(hours=hours),
                finished_at=now - timedelta(hours=hours) + timedelta(minutes=1),
                items_found=5,
                items_new=5 if hours == 30 else 0,
            )
        )
    return s


def _opportunity(item: DemoItem, source: Source, now: datetime) -> Opportunity:
    today = now.astimezone(KIGALI).date()
    is_original = source.kind == "original"
    verification = verification_for([(is_original, source.kind)])
    event_start = event_end = deadline = None
    if item.stream == "event":
        event_start = _at(today, item.days, 9)
        event_end = _at(today, item.days + item.event_days, 18)
    else:
        deadline = _at(today, item.days, 17)
    evidence = {DEMO_MARK: True}
    evidence["_trust"] = trust_state(verification, evidence)
    amount, currency = item.value or (None, None)
    return Opportunity(
        stream=item.stream,
        subtype=item.subtype,
        title=item.title,
        organisation=item.organisation,
        organisation_short=item.organisation_short,
        summary=item.summary,
        published_at=now - timedelta(days=2),
        deadline_at=deadline,
        event_start=event_start,
        event_end=event_end,
        value_amount=Decimal(amount) if amount is not None else None,
        value_currency=currency,
        value_note=item.value_note,
        location=item.location,
        eligibility=item.eligibility,
        requirements=list(item.requirements) or None,
        tags=list(item.tags),
        evidence=evidence,
        status=status_for("open", item.stream, deadline, event_start, event_end, now),
        verification=verification,
        visibility="public",
        **item.extra,
    )


def demo_seed(
    db: Session,
    *,
    env: str,
    admin_email: str | None,
    now: datetime | None = None,
) -> DemoResult:
    """Load the demo catalogue and score it for the bootstrap admin. The caller
    commits. Raises ``DemoRefused`` outside dev or over real data."""
    if env != "dev":
        raise DemoRefused(
            f"BK_ENV is {env!r}; the demo seed runs only when it is 'dev'"
        )
    n = non_demo_count(db)
    if n:
        raise DemoRefused(
            f"the database already has {n} non-demo opportunit"
            f"{'y' if n == 1 else 'ies'}; the demo seed only runs on a dev "
            "database without real data"
        )
    try:
        admin = bootstrap(db, admin_email).user
    except ValueError as e:
        raise DemoRefused(str(e)) from None
    now = now or datetime.now(UTC)

    replaced = db.execute(sa.delete(Opportunity).where(_demo_filter())).rowcount
    sources = {key: _source(db, spec, now) for key, spec in DEMO_SOURCES.items()}
    for item in DEMO_ITEMS:
        src = sources[item.source]
        opp = _opportunity(item, src, now)
        db.add(opp)
        db.flush()
        db.add(
            OpportunitySource(
                opportunity_id=opp.id,
                source_id=src.id,
                url=f"{src.home_url}notices/{item.slug}",
                is_original=src.kind == "original",
                first_seen=now - timedelta(days=1),
                last_seen=now - timedelta(hours=6),
            )
        )
    db.flush()
    # Real clock, not ``now``: bootstrap stamps its requests with the real time.
    started = datetime.now(UTC)
    pids = list(
        db.scalars(
            sa.select(Profile.id).where(
                Profile.user_id == admin.id, Profile.active.is_(True)
            )
        )
    )
    # Rules only: no model, no embedder, so no keys and no network.
    stats = scoring.score_user(
        db,
        admin.id,
        deps=scoring.ScoringDeps(
            llm=None, embedder=None, settings=get_scoring_settings()
        ),
        now=now,
    )
    clear_requests(db, pids, started)  # scored: the first worker tick need not repeat
    return DemoResult(
        items=len(DEMO_ITEMS),
        sources=len(sources),
        replaced=replaced,
        stats=stats,
        admin_email=admin.email,
    )
