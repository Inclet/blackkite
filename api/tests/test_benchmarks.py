"""Benchmarks API (docs/api-contract.md section 6): robust statistics per category
and currency, the awards behind them, and detail.benchmark on tenders."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from blackkite.db.models import Award
from tests import factories as f
from tests.factories import NOW
from tests.member_helpers import *

_N = iter(range(10_000))


def award(db, src, category="transport", amount="1000000", currency="RWF", **kw):
    n = next(_N)
    a = Award(
        ref_key=kw.pop("ref_key", f"ref-{n}"),
        tender_ref=kw.pop("tender_ref", f"EX/{n}/2026"),
        entity=kw.pop("entity", "Example Agency (fictional)"),
        entity_key=kw.pop("entity_key", "example agency fictional"),
        title=kw.pop("title", f"Award {n}"),
        category=category,
        tags=[f"sector:{category}"],
        amount=Decimal(amount) if amount is not None else None,
        currency=currency if amount is not None else None,
        source_id=src.id,
        **kw,
    )
    db.add(a)
    db.flush()
    return a


@pytest.fixture
def src(db):
    return f.source(db, "Awards portal", kind="original", streams=["tender"])


def bidders(n):
    return [{"name": f"Bidder {i} (fictional)"} for i in range(n)]


def test_statistics_per_category_and_currency(db, src, ana, login):
    for amt, nb in (("1000000", 2), ("2000000", 3), ("3000000", 4), ("4000000", 5)):
        award(db, src, amount=amt, bidders=bidders(nb), awarded_on=date(2026, 9, 1))
    award(db, src, amount="500", currency="USD")  # never mixed with RWF
    award(db, src, amount=None)  # no price: counts only
    award(db, src, category="ict", amount="10")
    award(db, src, category="ict", amount="20")
    db.commit()
    r = login("ana@example.com").get("/api/benchmarks")
    assert r.status_code == 200, r.text
    cats = r.json()["categories"]
    assert [(c["category"], c["currency"], c["awards"]) for c in cats] == [
        ("transport", "RWF", 4),
        ("transport", "USD", 1),
        ("transport", None, 1),
        ("ict", "RWF", 2),
    ]
    rwf = cats[0]
    assert rwf["label"] == "Transport and logistics"
    assert (rwf["median"], rwf["p25"], rwf["p75"]) == (
        "2500000.00",
        "1750000.00",
        "3250000.00",
    )
    assert (rwf["min"], rwf["max"], rwf["medianBidders"]) == (
        "1000000.00",
        "4000000.00",
        3.5,
    )
    for c in cats[1:]:  # fewer than 3: counts only
        assert c["median"] is None and c["min"] is None and c["medianBidders"] is None


def test_filters_window_entity_and_hidden_sources(db, src, ana, login):
    testing = f.source(db, "Testing portal", status="testing", streams=["tender"])
    for d in (date(2026, 1, 5), date(2026, 6, 5), date(2026, 10, 5)):
        award(db, src, awarded_on=d)
    award(db, src, entity="Other Board (fictional)", entity_key="other board fictional")
    award(db, testing)  # testing sources' awards are hidden
    db.commit()
    c = login("ana@example.com")

    def count(**params):
        r = c.get("/api/benchmarks", params=params)
        assert r.status_code == 200, r.text
        return sum(x["awards"] for x in r.json()["categories"])

    assert count() == 4
    assert count(**{"from": "2026-06-01"}) == 2
    assert count(**{"from": "2026-02-01", "to": "2026-07-01"}) == 1
    assert count(entity="other board") == 1
    assert count(category="ict") == 0
    r = c.get("/api/benchmarks", params={"from": "2026-06-01", "to": "2026-01-01"})
    assert r.status_code == 422
    assert r.json()["detail"] == "The end date must be on or after the start date."
    assert c.get("/api/benchmarks", params={"category": "nope"}).status_code == 422


def test_awards_list_paged_with_bidders(db, src, ana, login):
    tender = f.opportunity(db, "Transport of maize (fictional)")
    f.link(db, tender, src, is_original=True)
    first = award(
        db,
        src,
        amount="6250000",
        winner="Example Haulage (fictional)",
        awarded_on=date(2026, 10, 14),
        prices=[
            {
                "bidder": "Example Haulage (fictional)",
                "amount": "6250000.00",
                "currency": "RWF",
            },
            {"bidder": "Example Movers (fictional)", "amount": None, "currency": None},
        ],
        url="https://awards.example/a/1",
        opportunity_id=tender.id,
    )
    for i in range(3):
        award(db, src, awarded_on=date(2026, 1, 1 + i))
    db.commit()
    c = login("ana@example.com")
    r = c.get("/api/benchmarks/transport", params={"limit": 2})
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["category"], out["label"], out["total"]) == (
        "transport",
        "Transport and logistics",
        4,
    )
    top = out["awards"][0]
    assert top == {
        "id": str(first.id),
        "tenderRef": first.tender_ref,
        "entity": "Example Agency (fictional)",
        "title": first.title,
        "winner": "Example Haulage (fictional)",
        "winningPrice": "6250000.00",
        "currency": "RWF",
        "bidders": [
            {"name": "Example Haulage (fictional)", "price": "6250000.00"},
            {"name": "Example Movers (fictional)"},
        ],
        "awardedOn": "2026-10-14",
        "url": "https://awards.example/a/1",
        "opportunityId": str(tender.id),
    }
    assert len(out["awards"]) == 2
    page2 = c.get("/api/benchmarks/transport", params={"limit": 2, "offset": 2}).json()
    assert len(page2["awards"]) == 2
    assert c.get("/api/benchmarks/nope").status_code == 404
    assert (
        c.get("/api/benchmarks/transport", params={"currency": "rwf"}).status_code
        == 422
    )


def test_session_required(client):
    for path in ("/api/benchmarks", "/api/benchmarks/transport", "/api/plans"):
        assert client.get(path).status_code == 401


def test_detail_benchmark_on_tenders_only(db, src, ana, login):
    tender = f.opportunity(db, "Refrigerated transport of vaccines (fictional)")
    f.link(db, tender, src, is_original=True)
    event = f.opportunity(
        db,
        "Logistics transport summit (fictional)",
        stream="event",
        event_start=NOW,
    )
    f.link(db, event, src, is_original=True)
    lonely = f.opportunity(db, "Construction of a classroom block (fictional)")
    f.link(db, lonely, src, is_original=True)
    for amt in ("1000000", "2000000", "3000000"):
        award(db, src, amount=amt)
    award(db, src, category="construction", amount="5")
    award(db, src, category="construction", amount="6")
    db.commit()
    c = login("ana@example.com")
    detail = c.get(f"/api/opportunities/{tender.id}").json()["detail"]
    assert detail["benchmark"] == {
        "category": "transport",
        "label": "Transport and logistics",
        "awards": 3,
        "currency": "RWF",
        "median": "2000000.00",
        "p25": "1500000.00",
        "p75": "2500000.00",
        "min": "1000000.00",
        "max": "3000000.00",
    }
    assert "benchmark" not in c.get(f"/api/opportunities/{event.id}").json()["detail"]
    assert "benchmark" not in c.get(f"/api/opportunities/{lonely.id}").json()["detail"]
