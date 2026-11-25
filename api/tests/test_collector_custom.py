"""custom collector type: allowlisted classes only; the JSON-LD events example.
Offline; the listing page is a synthetic file under tests/data/pages."""

import uuid
from pathlib import Path

import pytest

from blackkite.collectors import custom, registry
from blackkite.collectors.base import CollectorError
from blackkite.collectors.registry import build_collector, validate_config
from blackkite.db.models import Source
from tests.fakes import FakeWeb, make_client

PAGES = Path(__file__).parent / "data" / "pages"
H = "events.example"
CFG = {"collector": "jsonld_events", "options": {"list_url": f"https://{H}/kigali"}}


def source(config=CFG) -> Source:
    return Source(
        id=uuid.uuid4(),
        name="Events",
        home_url=f"https://{H}",
        streams=["event"],
        kind="publisher",
        collector_type="custom",
        config=config,
        rate_limit=2.0,
    )


def web_with_events() -> FakeWeb:
    web = FakeWeb()
    web.html(H, "/kigali", (PAGES / "events.html").read_text())
    return web


def test_jsonld_events_parsed():
    web = web_with_events()
    items = build_collector("custom", make_client(web)).fetch(source())
    by_url = {i.url: i for i in items}
    assert list(by_url) == [
        f"https://{H}/e/logistics-forum-2027",
        f"https://{H}/e/ai",
        f"https://{H}/e/food",
    ]
    f = by_url[f"https://{H}/e/logistics-forum-2027"]
    assert f.title == "Kigali Logistics & Trade Forum 2027"
    assert f.organisation == "Example Chamber"
    assert f.snippet == "Two days on regional freight."
    assert f.listed_deadline is None  # events carry dates in extra, not a deadline
    assert f.extra == {
        "event_start": "2027-03-10T09:00:00+02:00",
        "event_end": "2027-03-11T17:00:00+02:00",
        "location": "Example Convention Centre, Kigali, Rwanda",
        "event_status": "EventScheduled",
        "attendance_mode": "OfflineEventAttendanceMode",
        "price": "50 USD",
        "offers_valid_through": "2027-03-01",
        "jsonld_type": "BusinessEvent",
    }
    ai = by_url[f"https://{H}/e/ai"]
    assert ai.organisation == "Group A, Group B"
    assert ai.extra["location"] == "Online"
    assert ai.extra["price"] == "0 RWF"
    food = by_url[f"https://{H}/e/food"]
    assert (
        food.extra["location"] == "Kigali" and food.extra["jsonld_type"] == "Festival"
    )
    assert web.paths() == ["/robots.txt", "/kigali"]


def test_max_items_and_pagination():
    web = web_with_events()
    web.html(H, "/kigali?page=2", "<html><body>no json-ld</body></html>")
    cfg = {
        "collector": "jsonld_events",
        "options": {
            "list_url": f"https://{H}/kigali",
            "pagination_pattern": f"https://{H}/kigali?page={{page}}",
            "max_pages": 3,
        },
    }
    items = build_collector("custom", make_client(web)).fetch(source(cfg))
    assert len(items) == 3
    assert web.paths() == ["/robots.txt", "/kigali", "/kigali?page=2"]  # stopped
    cfg["options"]["max_items"] = 1
    assert len(build_collector("custom", make_client(web)).fetch(source(cfg))) == 1


@pytest.mark.parametrize(
    "config, match",
    [
        ({"collector": "os.system", "options": {}}, "unknown custom collector"),
        ({"collector": "blackkite.collectors.rss.RssCollector"}, "unknown custom"),
        ({"collector": "jsonld_events", "module": "os"}, "Extra inputs"),
        ({"collector": "jsonld_events", "options": {}}, "invalid options"),
        (
            {"collector": "jsonld_events", "options": {"list_url": "http://[::1]/"}},
            "not public",
        ),
        (
            {
                "collector": "jsonld_events",
                "options": {"list_url": f"https://{H}/", "class_path": "x.Y"},
            },
            "Extra inputs",
        ),
        ({}, "collector"),
    ],
)
def test_only_allowlisted_classes_and_valid_options(config, match):
    with pytest.raises(ValueError, match=match):
        validate_config("custom", config)
    with pytest.raises(CollectorError):
        build_collector("custom", make_client(FakeWeb())).fetch(source(config))


def test_config_normalised_and_form():
    assert validate_config("custom", CFG) == {
        "collector": "jsonld_events",
        "options": {
            "list_url": f"https://{H}/kigali",
            "first_page": 2,
            "max_pages": 1,
            "max_items": 100,
        },
    }
    form = registry.config_form("custom")
    (collector,) = [f for f in form["fields"] if f["name"] == "collector"]
    assert collector["type"] == "enum"
    assert collector["choices"] == ["demo_fictional", "jsonld_events"]
    assert set(form["collectors"]) == set(custom.CUSTOM_COLLECTORS)
    names = {f["name"] for f in form["collectors"]["jsonld_events"]["fields"]}
    assert {"list_url", "max_items"} <= names


def test_hostile_jsonld_is_bounded():
    deep = "[" * 50_000 + "]" * 50_000
    many = (
        "["
        + ",".join('{"@type":"Event","name":"x","url":"/e"}' for _ in range(3))
        + "]"
    )
    page = (
        f'<script type="application/ld+json">{deep}</script>'
        f'<script type="application/ld+json">{many}</script>'
    )
    events = custom.find_events(custom.jsonld_nodes(page))
    assert len(events) == 3


def test_demo_fictional_is_a_no_op_with_no_options():
    cfg = {"collector": "demo_fictional", "options": {}}
    assert validate_config("custom", cfg) == cfg
    with pytest.raises(ValueError, match="invalid options for demo_fictional"):
        validate_config("custom", {"collector": "demo_fictional", "options": {"x": 1}})
    assert (
        registry.config_form("custom")["collectors"]["demo_fictional"]["fields"] == []
    )
