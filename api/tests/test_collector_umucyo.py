"""umucyo_awards and umucyo_plans custom collectors. Offline: synthetic pages under
tests/data/pages, served by FakeWeb (real Umucyo markup is untested until M0)."""

import uuid
from pathlib import Path

import httpx
import pytest

from blackkite.collectors.base import CollectorError, RawBidder, collected_records
from blackkite.collectors.registry import build_collector, validate_config
from blackkite.db.models import Source
from tests.fakes import FakeWeb, make_client

PAGES = Path(__file__).parent / "data" / "pages"
H = "procurement.example"

AWARDS_CFG = {
    "collector": "umucyo_awards",
    "options": {
        "list_url": f"https://{H}/awards",
        "selectors": {
            "item": "table.awards tbody tr",
            "tender_ref": "td:nth-child(1)",
            "title": "td:nth-child(2)",
            "entity": "td:nth-child(3)",
            "winner": "td:nth-child(4)",
            "amount": "td:nth-child(5)",
            "award_date": "td:nth-child(6)",
        },
        "detail": {
            "selectors": {
                "period": ".period",
                "bidders": {"row": "ul.bids li", "name": ".bidder", "price": ".price"},
            }
        },
        "date_formats": ["%d/%m/%Y"],
    },
}
PLANS_CFG = {
    "collector": "umucyo_plans",
    "options": {
        "list_url": f"https://{H}/plans",
        "selectors": {
            "item": "table.plan tr",
            "description": "td:nth-child(1)",
            "method": "td:nth-child(2)",
            "estimated_value": "td:nth-child(3)",
            "planned_quarter": "td:nth-child(4)",
        },
        "page": {"entity": "h1.entity", "fiscal_year": "p.fy"},
        "quarter_basis": "fiscal",
        "amounts": {"currency": "RWF"},
    },
}


def source(config) -> Source:
    return Source(
        id=uuid.uuid4(),
        name="Procurement portal (test)",
        home_url=f"https://{H}",
        streams=["tender"],
        kind="original",
        collector_type="custom",
        config=config,
        rate_limit=2.0,
    )


def web() -> FakeWeb:
    w = FakeWeb()
    w.html(H, "/awards", (PAGES / "awards-list.html").read_text())
    w.html(H, "/awards/1", (PAGES / "award-1.html").read_text())
    w.html(H, "/plans", (PAGES / "plans-list.html").read_text())
    return w


def test_awards_from_list_and_detail_pages():
    w = web()
    collector = build_collector("custom", make_client(w))
    assert collector.fetch(source(AWARDS_CFG)) == []  # never opportunities
    rec = collected_records(collector)
    assert rec is not None and rec.kind == "award"
    assert rec.formats.date_formats == ("%d/%m/%Y",)
    first, second = rec.items
    assert first.url == f"https://{H}/awards/1"
    assert first.tender_ref == "EX/001/G/2026"
    assert first.title == "Transport of maize from district stores"
    assert first.entity == "Procuring entity: Example Grain Agency (fictional)"
    assert first.amount == "FRW 6,250,000" and first.award_date == "14/10/2026"
    assert first.period == "12 months"
    assert first.bidders == (
        RawBidder("Example Haulage Ltd (fictional)", "FRW 6,250,000"),
        RawBidder("Example Movers (fictional)", "FRW 7,100,000"),
        RawBidder("Example Logistics Co (fictional)", "not read out"),
    )
    assert second.bidders == () and second.award_date == "3 Nov"
    kinds = [x["kind"] for x in collector.warnings]
    assert kinds == ["record_skipped", "record_skipped"]  # spacer row, 404 page
    assert "no tender ref or title" in collector.warnings[0]["message"]
    assert w.paths() == ["/robots.txt", "/awards", "/awards/1", "/awards/2"]


def test_awards_preview_reads_the_first_page_and_few_details():
    w = web()
    cfg = {
        **AWARDS_CFG,
        "options": {
            **AWARDS_CFG["options"],
            "pagination_pattern": f"https://{H}/awards?page={{page}}",
            "max_pages": 5,
        },
    }
    collector = build_collector("custom", make_client(w), preview=True)
    collector.fetch(source(cfg))
    assert len(collected_records(collector).items) == 2
    assert "/awards?page=2" not in w.paths()


def test_robots_disallow_stops_the_collector():
    w = web()
    w.add(
        H,
        "/robots.txt",
        httpx.Response(200, text="User-agent: *\nDisallow: /awards\n"),
    )
    with pytest.raises(CollectorError):
        build_collector("custom", make_client(w)).fetch(source(AWARDS_CFG))
    assert "/awards" not in w.paths()


def test_plans_with_page_level_entity_and_fiscal_year():
    w = web()
    collector = build_collector("custom", make_client(w))
    assert collector.fetch(source(PLANS_CFG)) == []
    rec = collected_records(collector)
    assert rec.kind == "plan"
    assert rec.formats.quarter_basis == "fiscal" and rec.formats.currency == "RWF"
    assert [p.description for p in rec.items] == [
        "Transport of bagged grain to regional stores",
        "Supply of office furniture",
        "Development of a stock management information system",
    ]
    p = rec.items[0]
    assert p.entity == "Example Grain Agency (fictional)"
    assert p.fiscal_year == "Procurement plan, fiscal year 2026/2027"
    assert p.planned_quarter == "Q3" and p.estimated_value == "RWF 40,000,000"
    assert p.method == "Open competitive bidding"
    assert p.url == f"https://{H}/plans"  # no per-row link: the plan page
    assert [x["message"] for x in collector.warnings] == [
        f"plan entry on https://{H}/plans has no description"
    ]


@pytest.mark.parametrize(
    "options, match",
    [
        (
            {**PLANS_CFG["options"], "quarter_basis": None},
            "quarter_basis is required",
        ),
        (
            {**AWARDS_CFG["options"], "date_formats": ["%d %b"]},
            "has no year",
        ),
        (
            {
                **AWARDS_CFG["options"],
                "amounts": {"decimal_separator": ",", "thousands_separators": [","]},
            },
            "decimal separator cannot also be",
        ),
        (
            {**AWARDS_CFG["options"], "list_url": "http://10.0.0.1/awards"},
            "not public",
        ),
        (
            {
                **AWARDS_CFG["options"],
                "selectors": {"item": "tr", "entity": "td"},
            },
            "set tender_ref or title",
        ),
        (
            {**AWARDS_CFG["options"], "selectors": {"item": "tr[", "title": "td"}},
            "invalid CSS selector",
        ),
        ({**AWARDS_CFG["options"], "module": "os"}, "is not a setting"),
    ],
)
def test_options_refused(options, match):
    collector = (
        "umucyo_plans" if "quarter_basis" in options or "page" in options else None
    )
    collector = collector or "umucyo_awards"
    with pytest.raises(ValueError, match=match):
        validate_config("custom", {"collector": collector, "options": options})


def test_options_normalised_on_save():
    saved = validate_config("custom", PLANS_CFG)
    assert saved["collector"] == "umucyo_plans"
    assert saved["options"]["selectors"]["description"] == {"css": "td:nth-child(1)"}
    assert saved["options"]["amounts"]["currency"] == "RWF"
