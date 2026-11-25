"""json_api collector: field mapping, pagination, guard, size cap. Offline."""

import json
import uuid

import httpx
import pytest

from blackkite.collectors.base import CollectorError
from blackkite.collectors.http import ResponseTooLarge
from blackkite.collectors.json_api import lookup
from blackkite.collectors.registry import build_collector, validate_config
from blackkite.db.models import Source
from tests.fakes import FakeWeb, make_client

H = "portal.example"
EP = f"https://{H}/api/notices"


def source(config) -> Source:
    return Source(
        id=uuid.uuid4(),
        name="API",
        home_url=f"https://{H}",
        streams=["tender"],
        kind="original",
        collector_type="json_api",
        config=config,
        rate_limit=2.0,
    )


def js(data, **headers):
    return httpx.Response(
        200,
        content=json.dumps(data).encode(),
        headers={"content-type": "application/json", **headers},
    )


MAPPING = {
    "list": "data.items",
    "title": "title",
    "url": "links.self",
    "date": "published",
    "deadline": "dates.closing",
    "organisation": "buyer.name",
    "snippet": "body",
    "extra": {"reference": "ref", "tags": "tags"},
}


def page(*rows, nxt=None):
    out = {"data": {"items": list(rows)}}
    if nxt is not None:
        out["links"] = {"next": nxt}
    return out


ROW1 = {
    "title": "Supply of <b>cold</b> rooms",
    "links": {"self": "/notice/1"},
    "published": "2026-11-20",
    "dates": {"closing": "2026-12-10T10:00:00+02:00"},
    "buyer": {"name": "Ministry of Examples"},
    "body": "<p>Two cold rooms.</p>",
    "ref": 1234,
    "tags": ["cold chain", "logistics"],
}


def collect(web, config, preview=False):
    return build_collector("json_api", make_client(web), preview=preview).fetch(
        source(config)
    )


def test_maps_fields_and_resolves_links():
    web = FakeWeb()
    seen = []

    def handler(req):
        seen.append(req)
        return js(
            page(
                ROW1,
                {"title": "No link"},
                {"title": "Internal", "links": {"self": "http://192.168.1.1/x"}},
                {"links": {"self": "/notice/9"}},  # no title
                "not an object",
                {"title": "Dup", "links": {"self": "/notice/1"}},
            )
        )

    web.add(H, "/api/notices", handler)
    items = collect(
        web, {"endpoint": EP, "params": {"country": "RW"}, "mapping": MAPPING}
    )
    (it,) = items
    assert it.url == f"https://{H}/notice/1"
    assert it.title == "Supply of cold rooms"
    assert it.listed_published == "2026-11-20"
    assert it.listed_deadline == "2026-12-10T10:00:00+02:00"
    assert it.organisation == "Ministry of Examples"
    assert it.snippet == "Two cold rooms."
    assert it.extra == {"reference": "1234", "tags": "cold chain, logistics"}
    (req,) = seen
    assert req.url.params["country"] == "RW"
    assert req.headers["accept"] == "application/json"
    assert req.method == "GET"


def test_url_template_and_root_array():
    web = FakeWeb()
    web.add(H, "/api/notices", js([{"name": "Notice A", "id": "A/1 2"}]))
    cfg = {
        "endpoint": EP,
        "mapping": {
            "title": "name",
            "url": "id",
            "url_template": f"https://{H}/Public/Notice/{{value}}",
        },
    }
    (it,) = collect(web, cfg)
    assert it.url == f"https://{H}/Public/Notice/A%2F1%202"


def test_page_pagination_stops_at_empty_page():
    web = FakeWeb()

    def handler(req):
        n = int(req.url.params["page"])
        rows = [] if n >= 3 else [{"title": f"T{n}", "links": {"self": f"/n/{n}"}}]
        return js(page(*rows))

    web.add(H, "/api/notices", handler)
    cfg = {
        "endpoint": EP,
        "params": {"page": 99, "size": 10},
        "pagination": {"mode": "page", "param": "page", "start": 1, "max_pages": 5},
        "mapping": MAPPING,
    }
    items = collect(web, cfg)
    assert [i.title for i in items] == ["T1", "T2"]
    pages = [r.url.params["page"] for r in web.requests if r.url.path != "/robots.txt"]
    assert pages == ["1", "2", "3"]
    assert len(collect(web, cfg, preview=True)) == 1


def test_next_link_pagination_same_host_only():
    web = FakeWeb()
    web.add(
        H,
        "/api/notices",
        js(page({"title": "P1", "links": {"self": "/n/1"}}, nxt="/api/notices/p2?c=x")),
    )
    web.add(
        H,
        "/api/notices/p2",
        js(page({"title": "P2", "links": {"self": "/n/2"}}, nxt="/api/notices")),
    )
    cfg = {
        "endpoint": EP,
        "pagination": {"mode": "next_link", "path": "links.next", "max_pages": 5},
        "mapping": MAPPING,
    }
    assert [i.title for i in collect(web, cfg)] == ["P1", "P2"]  # loop stopped

    web2 = FakeWeb()
    web2.add(
        H,
        "/api/notices",
        js(
            page(
                {"title": "P1", "links": {"self": "/n/1"}}, nxt="https://evil.example/"
            )
        ),
    )
    with pytest.raises(CollectorError, match="leaves the endpoint's host"):
        collect(web2, cfg)
    assert all(r.headers["host"] == H for r in web2.requests)


def test_size_cap_and_bad_json():
    web = FakeWeb()
    web.add(H, "/api/notices", js({"data": {"items": [{"title": "x" * 5000}]}}))
    with pytest.raises(ResponseTooLarge):
        collect(web, {"endpoint": EP, "mapping": MAPPING, "max_bytes": 1000})
    web.add(H, "/api/notices", httpx.Response(200, text="<html>nope</html>"))
    with pytest.raises(CollectorError, match="invalid JSON"):
        collect(web, {"endpoint": EP, "mapping": MAPPING})
    web.add(H, "/api/notices", httpx.Response(200, text="[" * 100_000 + "]" * 100_000))
    with pytest.raises(CollectorError):
        collect(web, {"endpoint": EP, "mapping": MAPPING, "max_bytes": 5_000_000})
    web.add(H, "/api/notices", js({"data": {"items": {"not": "a list"}}}))
    with pytest.raises(CollectorError, match="no array at data.items"):
        collect(web, {"endpoint": EP, "mapping": MAPPING})


def test_lookup():
    data = {"a": {"b": [{"c": 1}, {"c": 2}]}}
    assert lookup(data, "a.b.1.c") == 2
    assert lookup(data, "a.b.5.c") is None
    assert lookup(data, "a.x") is None
    assert lookup(data, "") is data
    assert lookup(data, "a.b.c") is None


@pytest.mark.parametrize(
    "config",
    [
        {"endpoint": "http://169.254.169.254/latest", "mapping": MAPPING},
        {"endpoint": EP},
        {"endpoint": EP, "mapping": {"title": "t"}},
        {"endpoint": EP, "mapping": {**MAPPING, "title": "a..b"}},
        {"endpoint": EP, "mapping": {**MAPPING, "url_template": "https://x.example/"}},
        {
            "endpoint": EP,
            "mapping": {**MAPPING, "url_template": "http://[::1]/{value}"},
        },
        {"endpoint": EP, "mapping": MAPPING, "pagination": {"mode": "cursor"}},
        {"endpoint": EP, "mapping": MAPPING, "max_bytes": 50_000_000},
        {"endpoint": EP, "mapping": MAPPING, "method": "POST"},
        {"endpoint": EP, "mapping": MAPPING, "params": {"q": {"nested": 1}}},
    ],
)
def test_bad_config_rejected(config):
    with pytest.raises(ValueError):
        validate_config("json_api", config)


def test_config_normalised():
    cfg = validate_config(
        "json_api",
        {
            "endpoint": EP,
            "mapping": {"title": "t", "url": "u"},
            "pagination": {"mode": "page"},
        },
    )
    assert cfg["pagination"] == {
        "mode": "page",
        "param": "page",
        "start": 1,
        "max_pages": 3,
    }
    assert cfg["max_bytes"] == 2_000_000
