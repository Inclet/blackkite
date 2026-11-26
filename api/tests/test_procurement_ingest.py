"""Awards and procurement plans through the runner, their ingest paths and links
to tenders; the admin test run previews records and writes nothing. Synthetic
pages only (tests/data/pages)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa

from blackkite.collectors.base import Formats, RawAward, RawBidder, RawItem, RawPlan
from blackkite.db.models import Award, Opportunity, ProcurementPlanItem, Source
from blackkite.pipeline import awards as A
from blackkite.pipeline import ingest
from blackkite.pipeline import plans as PL
from blackkite.routes.sources import get_preview_client_factory
from blackkite.worker import runner
from tests.conftest import make_user, sign_in
from tests.fakes import make_client
from tests.test_collector_umucyo import AWARDS_CFG, PLANS_CFG, H, web

NOW = datetime(2026, 11, 26, 9, 0, tzinfo=UTC)
TODAY = date(2026, 11, 26)


def add_source(db, config, name="Procurement portal (test)") -> Source:
    s = Source(
        name=name,
        home_url=f"https://{H}",
        streams=["tender"],
        kind="original",
        collector_type="custom",
        config=config,
        rate_limit=1.0,
        status="testing",
    )
    db.add(s)
    db.commit()
    return s


def add_tender(db, title, organisation, *, evidence=None, visibility="public", **kw):
    owner = None
    if visibility == "private":
        owner = make_user(db, f"owner-{uuid.uuid4().hex[:6]}@example.com").id
    o = Opportunity(
        stream="tender",
        title=title,
        organisation=organisation,
        evidence=evidence or {},
        visibility=visibility,
        owner_user_id=owner,
        **kw,
    )
    db.add(o)
    db.commit()
    return o


# --- normalising ------------------------------------------------------------------


def test_normalise_award_keeps_listed_text_and_never_guesses():
    raw = RawAward(
        source_id=uuid.uuid4(),
        url="https://x.example/a",
        fetched_at=NOW,
        tender_ref=" Ref: EX/9/2026 ",
        title="Supply of laptops",
        entity="Example Ministry (fictional)",
        winner="Example Computers (fictional)",
        amount="12,000",
        currency="USD",
        award_date="3 Nov",
        bidders=(RawBidder("Example Computers (fictional)", "12,000"),),
    )
    n = A.normalise_award(raw, Formats(), TODAY)
    assert n.tender_ref == "EX/9/2026" and n.ref_key == "ex/9/2026"
    assert (n.amount, n.currency) == (Decimal("12000.00"), "USD")
    assert n.awarded_on is None
    assert "award date: '3 Nov' has no year; not guessed" in n.problems
    assert n.prices == [
        {
            "bidder": "Example Computers (fictional)",
            "amount": "12000.00",
            "currency": "USD",
        }
    ]
    assert n.category == "ict" and n.tags == ["sector:ict"]
    assert n.raw["listed"]["award_date"] == "3 Nov"
    future = A.normalise_award(
        RawAward(
            raw.source_id,
            raw.url,
            NOW,
            title="Road works in Example District",
            award_date="1/1/2027",
        ),
        Formats(),
        TODAY,
    )
    assert future.awarded_on is None and "in the future" in future.problems[0]
    assert future.ref_key == "title:road works in example district"
    conflict = A.normalise_award(
        RawAward(
            raw.source_id, raw.url, NOW, title="T", amount="FRW 5", currency="USD"
        ),
        Formats(),
        TODAY,
    )
    assert conflict.amount is None and "disagrees" in conflict.problems[-1]


def test_normalise_plan_periods():
    sid = uuid.uuid4()
    base = {"source_id": sid, "url": "https://x.example/p", "fetched_at": NOW}
    fiscal = Formats(quarter_basis="fiscal")
    n = PL.normalise_plan(
        RawPlan(
            **base,
            entity="E (fictional)",
            description="Transport of grain",
            planned_quarter="Q3",
            fiscal_year="FY 2026/2027",
        ),
        fiscal,
        TODAY,
    )
    assert n.fiscal_year == "2026/27" and n.planned_quarter == "Q3"
    assert (n.planned_start, n.planned_end) == (date(2027, 1, 1), date(2027, 3, 31))
    no_year = PL.normalise_plan(
        RawPlan(
            **base, entity="E", description="Transport of grain", planned_quarter="Q3"
        ),
        fiscal,
        TODAY,
    )
    assert no_year.planned_start is None and "no stated year" in no_year.problems[0]
    dated = PL.normalise_plan(
        RawPlan(**base, entity="E", description="D", planned_date="15/02/2027"),
        Formats(),
        TODAY,
    )
    assert dated.planned_start == dated.planned_end == date(2027, 2, 15)
    assert PL.normalise_plan(RawPlan(**base, description="D"), Formats(), TODAY) is None


# --- runner -----------------------------------------------------------------------


def test_award_run_writes_awards_never_opportunities(db):
    s = add_source(db, AWARDS_CFG)
    run = runner.run_source(db, s, client=make_client(web()), now=lambda: NOW)
    assert run.status == "succeeded", run.error
    assert (run.items_found, run.items_new, run.items_failed) == (2, 2, 0)
    assert [w["kind"] for w in run.warnings] == ["record_skipped", "record_skipped"]
    assert db.scalar(sa.select(sa.func.count()).select_from(Opportunity)) == 0
    rows = {a.tender_ref: a for a in db.scalars(sa.select(Award))}
    maize = rows["EX/001/G/2026"]
    assert maize.entity == "Example Grain Agency (fictional)"
    assert (maize.amount, maize.currency) == (Decimal("6250000.00"), "RWF")
    assert maize.awarded_on == date(2026, 10, 14)
    assert maize.category == "transport" and maize.period == "12 months"
    assert maize.bidders == [
        {"name": "Example Haulage Ltd (fictional)"},
        {"name": "Example Movers (fictional)"},
        {"name": "Example Logistics Co (fictional)"},
    ]
    assert maize.prices[2] == {
        "bidder": "Example Logistics Co (fictional)",
        "amount": None,
        "currency": None,
    }
    assert maize.source_id == s.id and maize.url == f"https://{H}/awards/1"
    laptops = rows["EX/002/S/2026"]
    assert laptops.awarded_on is None  # "3 Nov": no year, not guessed
    assert laptops.raw["problems"] == [
        "award date: '3 Nov' matches none of the date formats; left out"
    ]

    later = NOW + timedelta(days=1)
    again = runner.run_source(db, s, client=make_client(web()), now=lambda: later)
    assert (again.items_found, again.items_new) == (2, 0)
    db.expire_all()
    assert db.scalar(sa.select(sa.func.count()).select_from(Award)) == 2
    assert db.get(Award, maize.id).last_seen == later


def test_award_links_to_tender_by_ref_or_title_and_entity(db):
    by_ref = add_tender(
        db,
        "Invitation for bids",
        "Example Grain Agency (fictional)",
        evidence={"_sources": {"x": {"title": "Tender EX/001/G/2026: transport"}}},
    )
    by_title = add_tender(
        db, "Supply of laptops", "Example Ministry of Data (fictional)"
    )
    add_tender(db, "Supply of laptops", "Another Ministry (fictional)")
    s = add_source(db, AWARDS_CFG)
    runner.run_source(db, s, client=make_client(web()), now=lambda: NOW)
    links = {a.tender_ref: a.opportunity_id for a in db.scalars(sa.select(Award))}
    assert links == {"EX/001/G/2026": by_ref.id, "EX/002/S/2026": by_title.id}


def test_private_items_are_never_linked(db):
    add_tender(
        db,
        "Supply of laptops",
        "Example Ministry of Data (fictional)",
        visibility="private",
    )
    s = add_source(db, AWARDS_CFG)
    runner.run_source(db, s, client=make_client(web()), now=lambda: NOW)
    assert all(a.opportunity_id is None for a in db.scalars(sa.select(Award)))


def test_plan_run_and_later_tender_links_it(db):
    s = add_source(db, PLANS_CFG)
    run = runner.run_source(db, s, client=make_client(web()), now=lambda: NOW)
    assert run.status == "succeeded", run.error
    assert (run.items_found, run.items_new) == (3, 3)
    assert db.scalar(sa.select(sa.func.count()).select_from(Opportunity)) == 0
    plans = {p.description: p for p in db.scalars(sa.select(ProcurementPlanItem))}
    grain = plans["Transport of bagged grain to regional stores"]
    assert grain.entity == "Example Grain Agency (fictional)"
    assert grain.fiscal_year == "2026/27" and grain.planned_quarter == "Q3"
    assert (grain.planned_start, grain.planned_end) == (
        date(2027, 1, 1),
        date(2027, 3, 31),
    )
    assert (grain.estimated_amount, grain.currency) == (Decimal("40000000.00"), "RWF")
    assert grain.method == "Open competitive bidding" and grain.category == "transport"
    furniture = plans["Supply of office furniture"]
    assert furniture.currency == "RWF"  # the config states the page's currency
    assert furniture.planned_start == date(2027, 4, 1)
    system = plans["Development of a stock management information system"]
    assert (system.currency, system.planned_start) == ("USD", None)
    assert all(p.opportunity_id is None for p in plans.values())

    # The tender is advertised later on another source: the plan gets linked.
    board = Source(
        name="Tender board (test)",
        home_url="https://board.example",
        streams=["tender"],
        kind="publisher",
        collector_type="html_list",
        config={},
    )
    db.add(board)
    db.commit()
    item = RawItem(
        source_id=board.id,
        url="https://board.example/n/1",
        title="Tender for transport of bagged grain to regional stores",
        fetched_at=NOW,
        organisation="Example Grain Agency (fictional)",
        listed_deadline="20 Jan 2027",
    )
    ingest.ingest_items(db, board, [item], deps=ingest.PipelineDeps(), now=NOW)
    db.commit()
    db.expire_all()
    tender = db.scalar(sa.select(Opportunity))
    assert db.get(ProcurementPlanItem, grain.id).opportunity_id == tender.id
    assert db.get(ProcurementPlanItem, furniture.id).opportunity_id is None
    assert db.scalar(sa.select(sa.func.count()).select_from(Opportunity)) == 1


def test_plan_not_linked_to_a_tender_from_long_before_its_year(db):
    add_tender(
        db,
        "Transport of bagged grain to regional stores",
        "Example Grain Agency (fictional)",
        published_at=datetime(2025, 6, 1, tzinfo=UTC),
    )
    s = add_source(db, PLANS_CFG)
    runner.run_source(db, s, client=make_client(web()), now=lambda: NOW)
    assert all(
        p.opportunity_id is None for p in db.scalars(sa.select(ProcurementPlanItem))
    )


# --- test run ---------------------------------------------------------------------


@pytest.fixture
def admin(app, client, db, outbox):
    w = web()
    app.dependency_overrides[get_preview_client_factory] = lambda: (
        lambda: make_client(w)
    )
    make_user(db, "admin@example.com", role="admin")
    return sign_in(client, outbox, "admin@example.com")


@pytest.mark.parametrize("config, kind", [(AWARDS_CFG, "award"), (PLANS_CFG, "plan")])
def test_test_run_previews_records_and_writes_nothing(admin, db, config, kind):
    r = admin.post(
        "/api/admin/sources/test-run",
        json={"homeUrl": f"https://{H}", "collectorType": "custom", "config": config},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and out["items"] == []
    assert {x["kind"] for x in out["records"]} == {kind}
    assert out["totalParsed"] == len(out["records"])
    if kind == "award":
        first = out["records"][0]
        assert first["tenderRef"] == "EX/001/G/2026"
        assert first["amount"] == "6250000.00" and first["currency"] == "RWF"
        assert first["categoryLabel"] == "Transport and logistics"
        assert first["bidders"][0] == {
            "name": "Example Haulage Ltd (fictional)",
            "price": "6250000.00",
        }
        assert out["records"][1]["problems"]
    else:
        first = out["records"][0]
        assert first["plannedLabel"] == "January to March 2027"
        assert first["estimatedValue"] == "40000000.00"
    for model in (Award, ProcurementPlanItem, Opportunity):
        assert db.scalar(sa.select(sa.func.count()).select_from(model)) == 0


# --- re-listing by another source; merging what a first listing left out --------


def _award(db, src, **kw):
    raw = RawAward(source_id=src.id, url="https://x.example/a", fetched_at=NOW, **kw)
    return A.upsert_award(db, src, A.normalise_award(raw, Formats(), TODAY), NOW)


def _plan(db, src, **kw):
    kw.setdefault("entity", "Example Board (fictional)")
    kw.setdefault("description", "Transport of grain to stores")
    raw = RawPlan(source_id=src.id, url="https://x.example/p", fetched_at=NOW, **kw)
    return PL.upsert_plan(db, src, PL.normalise_plan(raw, Formats(), TODAY), NOW)


def test_record_relisted_by_another_source_stays_visible_when_the_first_retires(
    db, client, outbox
):
    from blackkite.routes.member import now_utc

    first = add_source(db, AWARDS_CFG, name="First portal")
    second = add_source(db, AWARDS_CFG, name="Second portal")
    first.status = second.status = "active"
    for i in range(3):
        _award(
            db,
            first,
            tender_ref=f"EX/{i}/2026",
            title="Transport of maize",
            entity="Example Board (fictional)",
            amount="1,000,000",
            currency="RWF",
        )
    a, created = _award(
        db,
        second,
        tender_ref="EX/0/2026",
        title="Transport of maize",
        entity="Example Board (fictional)",
    )
    assert not created
    assert a.source_id == first.id and a.source_ids == [first.id, second.id]
    p, _ = _plan(db, first, fiscal_year="2026/27", planned_date="15 Jan 2027")
    p2, created = _plan(db, second, fiscal_year="2026/27")
    assert p2.id == p.id and not created and p.source_ids == [first.id, second.id]
    first.status = "retired"
    db.commit()

    client.app.dependency_overrides[now_utc] = lambda: NOW
    make_user(db, "ana@example.com")
    db.commit()
    c = sign_in(client, outbox, "ana@example.com")
    cats = c.get("/api/benchmarks").json()["categories"]
    # Only the award the second source also listed is still shown.
    assert sum(x["awards"] for x in cats) == 1
    second.status = "retired"
    db.commit()
    assert c.get("/api/benchmarks").json()["categories"] == []


def test_award_listing_that_adds_the_entity_merges(db):
    src = add_source(db, AWARDS_CFG)
    a, created = _award(db, src, tender_ref="EX/7/2026", title="Supply of desks")
    assert created and a.entity_key == ""
    b, created = _award(
        db,
        src,
        tender_ref="EX/7/2026",
        title="Supply of desks",
        entity="Example Ministry (fictional)",
        amount="900,000",
        currency="RWF",
    )
    assert not created and b.id == a.id
    assert b.entity == "Example Ministry (fictional)" and b.entity_key != ""
    # A later listing without the entity again still lands on the same row.
    c, created = _award(db, src, tender_ref="EX/7/2026", winner="Example Co")
    assert not created and c.id == a.id and c.entity_key == b.entity_key
    assert db.scalar(sa.select(sa.func.count()).select_from(Award)) == 1


def test_award_listing_without_entity_is_ambiguous_across_entities(db):
    src = add_source(db, AWARDS_CFG)
    _award(db, src, tender_ref="EX/8/2026", entity="Entity A (fictional)")
    _award(db, src, tender_ref="EX/8/2026", entity="Entity B (fictional)")
    _, created = _award(db, src, tender_ref="EX/8/2026")
    assert created  # two candidates: never guessed
    assert db.scalar(sa.select(sa.func.count()).select_from(Award)) == 3


def test_award_listing_that_adds_the_ref_merges_into_the_title_row(db):
    src = add_source(db, AWARDS_CFG)
    a, _ = _award(
        db, src, title="Supply of office desks", entity="Example Ministry (fictional)"
    )
    assert a.ref_key.startswith("title:")
    b, created = _award(
        db,
        src,
        tender_ref="EX/9/2026",
        title="Supply of office desks",
        entity="Example Ministry (fictional)",
    )
    assert not created and b.id == a.id and b.ref_key == "ex/9/2026"
    assert b.tender_ref == "EX/9/2026"


def test_plan_listing_that_adds_the_fiscal_year_merges(db):
    src = add_source(db, PLANS_CFG)
    p, created = _plan(db, src)
    assert created and p.fiscal_year is None
    q, created = _plan(db, src, fiscal_year="FY 2026/2027", estimated_value="5,000,000")
    assert not created and q.id == p.id and q.fiscal_year == "2026/27"
    r, created = _plan(db, src)  # the year left out again: same row
    assert not created and r.id == p.id and r.fiscal_year == "2026/27"
    # Another year is another plan item.
    _, created = _plan(db, src, fiscal_year="2027/28")
    assert created
    # Now two years: a listing without one is ambiguous and stored apart.
    _, created = _plan(db, src)
    assert created
    assert db.scalar(sa.select(sa.func.count()).select_from(ProcurementPlanItem)) == 3


def test_plan_matched_on_tender_ref_when_the_description_changes(db):
    src = add_source(db, PLANS_CFG)
    p, _ = _plan(db, src, tender_ref="PLAN/22/2026", fiscal_year="2026/27")
    q, created = _plan(
        db,
        src,
        description="Transport of grain to regional stores (lot 2)",
        tender_ref="plan/22/2026",
    )
    assert not created and q.id == p.id
    assert q.description == "Transport of grain to regional stores (lot 2)"


def _count_awards(db) -> int:
    return db.scalar(sa.select(sa.func.count()).select_from(Award))


def test_award_entity_merges_only_when_the_blank_row_is_the_only_one(db):
    src = add_source(db, AWARDS_CFG)
    _award(db, src, tender_ref="EX/10/2026", entity="Entity A (fictional)")
    _award(db, src, tender_ref="EX/10/2026", entity="Entity B (fictional)")
    blank, created = _award(db, src, tender_ref="EX/10/2026", title="Supply of desks")
    assert created and blank.entity_key == ""
    # Three rows share the ref, one blank: a listing from C is not guessed onto
    # the blank row (it could be A's, B's or C's).
    c, created = _award(db, src, tender_ref="EX/10/2026", entity="Entity C (fictional)")
    assert created and c.id != blank.id
    assert db.get(Award, blank.id).entity_key == ""
    assert _count_awards(db) == 4


def test_two_entities_with_the_same_generic_title_never_merge(db):
    src = add_source(db, AWARDS_CFG)
    a, _ = _award(db, src, title="Invitation for bids", entity="Entity A (fictional)")
    b, created = _award(
        db, src, title="Invitation for bids", entity="Entity B (fictional)"
    )
    assert created and b.id != a.id
    # No entity, no ref, generic title: never merged on title alone.
    c, created = _award(db, src, title="Invitation for bids", winner="Example Co")
    assert created and c.id not in {a.id, b.id}
    d, created = _award(db, src, title="Invitation for bids", winner="Other Co")
    assert created and d.id != c.id
    # The same listing again (title, entity, winner, amount all agree) is the
    # same row, so re-runs do not duplicate.
    e, created = _award(db, src, title="Invitation for bids", winner="Example Co")
    assert not created and e.id == c.id
    # A second, different award of the same entity under the same generic title.
    f, created = _award(
        db,
        src,
        title="Invitation for bids",
        entity="Entity A (fictional)",
        winner="Example Co",
        amount="2,000,000",
        currency="RWF",
    )
    assert created and f.id != a.id
    # A ref listing never adopts a generic title-keyed row.
    g, created = _award(
        db,
        src,
        tender_ref="EX/11/2026",
        title="Invitation for bids",
        entity="Entity A (fictional)",
    )
    assert created and g.ref_key == "ex/11/2026"
    assert _count_awards(db) == 6


def test_title_row_without_entity_never_absorbs_an_entity_listing(db):
    src = add_source(db, AWARDS_CFG)
    blank, _ = _award(db, src, title="Supply of office chairs")
    a, created = _award(
        db, src, title="Supply of office chairs", entity="Entity A (fictional)"
    )
    assert created and a.id != blank.id
    b, created = _award(
        db,
        src,
        tender_ref="EX/12/2026",
        title="Supply of office chairs",
        entity="Entity B (fictional)",
    )
    assert created and b.id not in {blank.id, a.id}
    assert db.get(Award, blank.id).entity_key == ""
    # The same entity with a ref still merges into its own title row.
    c, created = _award(
        db,
        src,
        tender_ref="EX/13/2026",
        title="Supply of office chairs",
        entity="Entity A (fictional)",
    )
    assert not created and c.id == a.id
    assert _count_awards(db) == 3
