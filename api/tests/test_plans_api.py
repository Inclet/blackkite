"""Plans API (docs/api-contract.md section 6): coming-up tenders matched to the
caller's own active profiles, cheaply (no model), within a window."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from blackkite.db.models import ProcurementPlanItem
from blackkite.member.procurement import planned_for
from blackkite.pipeline import categories
from blackkite.pipeline.procurement import description_key, entity_key
from tests import factories as f
from tests.member_helpers import *

_N = iter(range(10_000))


def plan(db, src, description, start=date(2027, 1, 1), end=date(2027, 3, 31), **kw):
    entity = kw.pop("entity", "Example Grain Agency (fictional)")
    cat = categories.categorise(description)
    p = ProcurementPlanItem(
        entity=entity,
        entity_key=entity_key(entity),
        description=description,
        description_key=description_key(description) + f" {next(_N)}",
        category=cat.category,
        tags=cat.tags,
        planned_start=start,
        planned_end=end,
        fiscal_year="2026/27",
        source_id=src.id,
        url="https://plans.example/p",
        **kw,
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture
def setup(db, ana):
    src = f.source(db, "Plans portal", kind="original", streams=["tender"])
    ironji = f.profile(
        db,
        ana,
        "Ironji-Trade",
        services=["dry freight", "cold chain", "last-mile distribution"],
        min_contract_rwf=5_000_000,
        exclusions={"organisations": ["Excluded Board"]},
    )
    ai = f.profile(
        db,
        ana,
        "AI lab",
        services=["software development", "AI/ML", "data"],
        provisional=True,
    )
    f.profile(
        db,
        ana,
        "Personal",
        type="personal",
        streams=["investment", "event"],
        instruments=["treasury bonds"],
        event_topics=["logistics and trade"],
    )
    f.profile(db, ana, "Old", services=["transport"]).active = False
    db.flush()
    return src, ironji, ai


def descriptions(client, **params):
    r = client.get("/api/plans", params=params)
    assert r.status_code == 200, r.text
    return [(i["description"], i["matchedProfile"]) for i in r.json()["items"]]


def test_plans_match_active_profiles_and_drop_advertised(db, setup, login):
    src, _, _ = setup
    testing = f.source(db, "Testing plans", status="testing", streams=["tender"])
    grain = plan(
        db,
        src,
        "Transport of bagged grain to regional stores",
        method="Open competitive bidding",
        estimated_amount=Decimal(40000000),
        currency="RWF",
        planned_quarter="Q3",
    )
    plan(
        db,
        src,
        "Transport of documents",
        estimated_amount=Decimal(1000000),
        currency="RWF",
    )  # below Ironji's minimum
    plan(
        db,
        src,
        "Development of a stock management information system",
        start=date(2027, 2, 15),
        end=date(2027, 2, 15),
    )
    plan(db, src, "Supply of office furniture")  # matches nobody
    plan(db, src, "Haulage of cement", entity="Excluded Board")
    plan(
        db,
        src,
        "Refrigerated transport later",
        start=date(2027, 7, 1),
        end=date(2027, 9, 30),
    )
    plan(
        db,
        src,
        "Cold chain transport in 2028",
        start=date(2028, 1, 1),
        end=date(2028, 3, 31),
    )
    plan(db, src, "Transport, no planned date", start=None, end=None)
    plan(db, testing, "Transport from a testing source")
    advertised = f.opportunity(db, "Tender: transport of fertiliser (fictional)")
    f.link(db, advertised, src, is_original=True)
    plan(db, src, "Transport of fertiliser", opportunity_id=advertised.id)
    hidden = f.opportunity(db, "Tender seen on a testing source only")
    f.link(db, hidden, testing, is_original=True)
    plan(db, src, "Transport of seedlings", opportunity_id=hidden.id)
    db.commit()

    c = login("ana@example.com")
    r = c.get("/api/plans")
    out = r.json()
    assert out["window"] == 12
    assert [(i["description"], i["matchedProfile"]) for i in out["items"]] == [
        ("Transport of bagged grain to regional stores", "Ironji-Trade"),
        ("Transport of seedlings", "Ironji-Trade"),
        ("Development of a stock management information system", "AI lab"),
        ("Refrigerated transport later", "Ironji-Trade"),
    ]
    first = out["items"][0]
    assert first == {
        "id": str(grain.id),
        "entity": "Example Grain Agency (fictional)",
        "description": "Transport of bagged grain to regional stores",
        "category": "transport",
        "categoryLabel": "Transport and logistics",
        "method": "Open competitive bidding",
        "estimatedValue": "40000000.00",
        "currency": "RWF",
        "plannedFor": "2027-Q1",
        "plannedStart": "2027-01-01",
        "plannedEnd": "2027-03-31",
        "plannedLabel": "January to March 2027",
        "fiscalYear": "2026/27",
        "quarter": "Q3",
        "matchedProfile": "Ironji-Trade",
        "provisional": False,
        "url": "https://plans.example/p",
    }
    ai = out["items"][2]
    assert ai["provisional"] is True and ai["plannedFor"] == "2027-02-15"
    assert "method" not in ai and "estimatedValue" not in ai

    assert [d for d, _ in descriptions(c, window="3")] == [
        "Transport of bagged grain to regional stores",
        "Transport of seedlings",
        "Development of a stock management information system",
    ]
    assert c.get("/api/plans", params={"window": "5"}).status_code == 422


def test_profile_filter_and_other_users(db, setup, login, ben):
    src, _ironji, ai = setup
    plan(db, src, "Transport of bagged grain")
    plan(db, src, "Development of a data platform")
    other = f.profile(db, ben, "Ben's", services=["transport"])
    db.commit()
    c = login("ana@example.com")
    assert descriptions(c, profile=str(ai.id)) == [
        ("Development of a data platform", "AI lab")
    ]
    assert c.get("/api/plans", params={"profile": str(other.id)}).status_code == 404
    personal_only = login("ben@example.com")
    other.active = False
    db.commit()
    assert descriptions(personal_only) == []


def test_one_shared_word_is_not_a_match(db, ana, login):
    """Review false matches: one shared word (or a weak word) no longer matches;
    a whole service, two distinct shared words, or the category does."""
    src = f.source(db, "Plans portal", kind="original", streams=["tender"])
    f.profile(
        db,
        ana,
        "Ironji-Trade",
        services=["dry freight", "cold chain", "last-mile distribution"],
    )
    f.profile(
        db,
        ana,
        "AI lab",
        services=["software development", "AI/ML", "data", "digital consulting"],
    )
    f.profile(
        db,
        ana,
        "Health NGO",
        organisation_type="Local NGO",
        services=["community health", "nutrition education"],
    )
    for d in (
        "Supply of dry foodstuffs for school feeding",  # "dry" alone
        "Supply chain audit of the district office",  # "chain" alone
        "Consultancy for a road feasibility study",  # "consulting" synonym only
        "Supply and installation of a solar system",  # "system" synonym only
        "Construction of a community hall",  # "community" alone
        "Construction of a health centre",  # "health" only, from a phrase
        "Rehabilitation of a feeder road",
    ):
        plan(db, src, d)
    plan(db, src, "Community health worker training")  # whole service
    plan(db, src, "Hire of trucks for election materials")  # category: transport
    plan(db, src, "Nutrition and health survey in Huye")  # two shared words
    plan(db, src, "Design of a data platform and software")  # whole terms
    db.commit()
    got = descriptions(login("ana@example.com"))
    assert sorted(got) == [
        ("Community health worker training", "Health NGO"),
        ("Design of a data platform and software", "AI lab"),
        ("Hire of trucks for election materials", "Ironji-Trade"),
        ("Nutrition and health survey in Huye", "Health NGO"),
    ]


def test_service_categories_need_one_category():
    from blackkite.db.models import Profile
    from blackkite.member.procurement import service_categories

    p = Profile(
        name="P",
        type="business",
        data={"services": ["dry freight", "digital consulting", "software"]},
    )
    assert service_categories(p) == {"transport", "ict"}


@pytest.mark.parametrize(
    "start, end, expected",
    [
        (date(2027, 2, 15), date(2027, 2, 15), "2027-02-15"),
        (date(2027, 2, 1), date(2027, 2, 28), "2027-02"),
        (date(2027, 1, 1), date(2027, 3, 31), "2027-Q1"),
        (date(2026, 10, 1), date(2026, 12, 31), "2026-Q4"),
        (date(2027, 2, 1), date(2027, 4, 30), "2027-02-01/2027-04-30"),
    ],
)
def test_planned_for_format(start, end, expected):
    assert planned_for(start, end) == expected
