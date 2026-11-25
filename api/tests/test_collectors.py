"""html_list and search_query collectors, and the type registry. Offline, synthetic data."""

import json
import uuid

import httpx
import pytest
from pydantic import SecretStr

from blackkite.collectors import registry
from blackkite.collectors.base import CollectorError
from blackkite.collectors.registry import build_collector, validate_config
from blackkite.db.models import COLLECTOR_TYPES, Source
from tests.fakes import FakeWeb, make_client

H = "notices.example"

LIST_PAGE_1 = """
<html><body>
  <div class="notice">
    <h3><a href="/n/101">Invitation for Bids: supply of cold storage</a></h3>
    <span class="org">Ministry of Examples</span>
    <span class="pub">9 Nov 2026</span>
    <span class="dl">Closes 30 Nov 2026, 5pm</span>
    <p class="sum">Supply   and installation of
      two cold rooms.</p>
  </div>
  <div class="notice">
    <h3><a href="https://other.example/n/102">Tenders for various items</a></h3>
    <span class="dl">7 Dec</span>
  </div>
  <div class="notice"><h3>No link here</h3></div>
  <div class="notice"><h3><a href="javascript:alert(1)">Script link</a></h3></div>
  <div class="notice"><h3><a href="/n/101">Duplicate of the first</a></h3></div>
</body></html>
"""

LIST_PAGE_2 = """
<html><body>
  <div class="notice"><h3><a href="/n/103">EOI: last-mile distribution</a></h3></div>
</body></html>
"""

DETAIL_101 = """
<html><body><h1>Invitation for Bids</h1>
  <div class="buyer">Ministry of Examples, Procurement Unit</div>
  <div class="deadline">Deadline: 1 December 2026 at 10:00</div>
  <div class="body">Bidders must hold a valid tax clearance.</div>
</body></html>
"""

BASE_CONFIG = {
    "list_url": f"https://{H}/tenders",
    "pagination_pattern": f"https://{H}/tenders?page={{page}}",
    "max_pages": 3,
    "selectors": {
        "item": "div.notice",
        "title": "h3",
        "organisation": ".org",
        "date": ".pub",
        "deadline": ".dl",
        "snippet": ".sum",
    },
}


def source(collector_type="html_list", config=None, rate_limit=2.0) -> Source:
    return Source(
        id=uuid.uuid4(),
        name="Test source",
        home_url=f"https://{H}",
        streams=["tender"],
        kind="publisher",
        collector_type=collector_type,
        config=config if config is not None else BASE_CONFIG,
        rate_limit=rate_limit,
    )


def web_with_pages() -> FakeWeb:
    web = FakeWeb()
    web.html(H, "/tenders", LIST_PAGE_1)
    web.html(H, "/tenders?page=2", LIST_PAGE_2)
    web.html(H, "/tenders?page=3", "<html><body><p>No more notices.</p></body></html>")
    web.html(H, "/n/101", DETAIL_101)
    return web


def test_html_list_parses_items_across_pages():
    web = web_with_pages()
    src = source()
    items = build_collector("html_list", make_client(web)).fetch(src)
    assert [i.url for i in items] == [
        f"https://{H}/n/101",
        "https://other.example/n/102",
        f"https://{H}/n/103",
    ]
    first = items[0]
    assert first.source_id == src.id
    assert first.title == "Invitation for Bids: supply of cold storage"
    assert first.organisation == "Ministry of Examples"
    assert first.listed_published == "9 Nov 2026"
    assert first.listed_deadline == "Closes 30 Nov 2026, 5pm"
    assert first.snippet == "Supply and installation of two cold rooms."
    assert first.fetched_at.tzinfo is not None
    assert items[1].listed_deadline == "7 Dec" and items[1].organisation is None
    assert web.paths(H) == [
        "/robots.txt",
        "/tenders",
        "/tenders?page=2",
        "/tenders?page=3",
    ]


def test_html_list_detail_pages_fill_and_override():
    web = web_with_pages()
    cfg = {
        **BASE_CONFIG,
        "max_pages": 1,
        "detail": {
            "selectors": {
                "deadline": ".deadline",
                "organisation": ".buyer",
                "snippet": ".body",
            }
        },
    }
    items = build_collector("html_list", make_client(web)).fetch(source(config=cfg))
    first, second = items
    assert first.detail_url == f"https://{H}/n/101"
    assert first.listed_deadline == "Deadline: 1 December 2026 at 10:00"
    assert first.organisation == "Ministry of Examples, Procurement Unit"
    assert first.snippet == "Bidders must hold a valid tax clearance."
    assert first.listed_published == "9 Nov 2026"  # not on the detail page: kept
    # other.example/n/102 is a 404: listing values kept, error noted, run continues
    assert second.listed_deadline == "7 Dec"
    assert "HTTP 404" in second.extra["detail_error"]


def test_html_list_link_selector_with_attribute():
    web = FakeWeb()
    web.html(
        H,
        "/l",
        '<ul><li data-url="/x/1"><b>Call for proposals</b></li></ul>',
    )
    cfg = {
        "list_url": f"https://{H}/l",
        "selectors": {
            "item": "li",
            "title": "b",
            "link": {"css": "li", "attr": "data-url"},
        },
    }
    # css_first on the item matches the item itself
    items = build_collector("html_list", make_client(web)).fetch(source(config=cfg))
    assert [(i.title, i.url) for i in items] == [
        ("Call for proposals", f"https://{H}/x/1")
    ]


def test_html_list_preview_fetches_first_page_only():
    web = web_with_pages()
    items = build_collector("html_list", make_client(web), preview=True).fetch(source())
    assert len(items) == 2
    assert web.paths(H) == ["/robots.txt", "/tenders"]


def test_html_list_uses_source_rate_limit():
    from tests.fakes import FakeClock

    web = web_with_pages()
    clock = FakeClock()
    build_collector("html_list", make_client(web, clock)).fetch(source(rate_limit=12.0))
    assert clock.sleeps == [12.0, 12.0, 12.0]


@pytest.mark.parametrize(
    ("config", "why"),
    [
        ({"placeholder": True}, "placeholder"),
        (
            {"list_url": "http://127.0.0.1/", "selectors": {"item": "a", "title": "a"}},
            "not public",
        ),
        (
            {
                "list_url": "file:///etc/passwd",
                "selectors": {"item": "a", "title": "a"},
            },
            "only http",
        ),
        (
            {"list_url": f"https://{H}/", "selectors": {"item": "div[", "title": "a"}},
            "invalid CSS",
        ),
        (
            {"list_url": f"https://{H}/", "selectors": {"item": "a"}},
            "Title selector: is required",
        ),
        (
            {
                "list_url": f"https://{H}/",
                "pagination_pattern": f"https://{H}/p",
                "selectors": {"item": "a", "title": "a"},
            },
            "{page}",
        ),
        (
            {
                "list_url": f"https://{H}/",
                "pagination_pattern": "https://10.0.0.1/?p={page}",
                "selectors": {"item": "a", "title": "a"},
            },
            "not public",
        ),
        (
            {
                "list_url": f"https://{H}/",
                "selectors": {"item": "a", "title": "a"},
                "eval": "x",
            },
            "Eval: is not a setting this accepts",
        ),
    ],
)
def test_html_list_bad_config_is_collector_error(config, why):
    with pytest.raises(CollectorError, match=why):
        build_collector("html_list", make_client(FakeWeb())).fetch(
            source(config=config)
        )
    with pytest.raises(ValueError, match=why):
        validate_config("html_list", config)


def test_html_list_site_error_is_collector_error():
    web = FakeWeb()
    web.add(H, "/tenders", httpx.Response(403))
    with pytest.raises(CollectorError, match="HTTP 403"):
        build_collector("html_list", make_client(web)).fetch(source())


def test_pagination_pattern_is_not_format_evaluated():
    cfg = {
        **BASE_CONFIG,
        "pagination_pattern": f"https://{H}/t?p={{page}}&x={{0.__class__}}",
    }
    parsed = validate_config("html_list", cfg)
    from blackkite.collectors.html_list import HtmlListConfig

    urls = HtmlListConfig.model_validate(parsed).page_urls()
    assert urls[1] == f"https://{H}/t?p=2&x={{0.__class__}}"


# --- search_query --------------------------------------------------------------------

BRAVE = "api.search.brave.com"

# Shaped like Brave's web search response (field names from memory; unverified live).
BRAVE_RESPONSE = {
    "type": "search",
    "query": {"original": "tender logistics site:notices.example"},
    "web": {
        "type": "search",
        "results": [
            {
                "title": "Invitation for <strong>Bids</strong> &amp; quotes: cold chain",
                "url": f"https://{H}/n/201",
                "description": "Closing date: <strong>4 Dec 2026</strong>. Supply of...",
                "page_age": "2026-11-20T08:00:00",
                "age": "5 days ago",
                "profile": {"name": "Notices Example"},
                "meta_url": {"hostname": H},
                "extra_snippets": ["Lot 1: <b>refrigerated</b> trucks", "Lot 2: dry"],
            },
            {
                "title": "Unrelated page elsewhere",
                "url": "https://elsewhere.example/x",
                "description": "Not on the restricted domain",
            },
            {"title": "Missing url"},
            {"title": "Bad scheme", "url": "ftp://notices.example/f"},
        ],
    },
}

SEARCH_CONFIG = {
    "queries": ["tender logistics", "tender cold chain"],
    "domains": [H],
    "recency_days": 7,
    "count": 10,
}


def brave_web(responses=None) -> FakeWeb:
    web = FakeWeb()
    web.add(
        BRAVE,
        "/res/v1/web/search",
        lambda req: httpx.Response(200, json=responses or BRAVE_RESPONSE),
    )
    return web


def test_search_query_maps_results_and_restricts_domain():
    from tests.fakes import FakeClock

    web = brave_web()
    clock = FakeClock()
    collector = build_collector(
        "search_query", make_client(web, clock), brave_api_key=SecretStr("k-123")
    )
    items = collector.fetch(source("search_query", SEARCH_CONFIG))
    assert len(items) == 1  # same URL in both queries; others filtered
    it = items[0]
    assert it.title == "Invitation for Bids & quotes: cold chain"
    assert it.url == f"https://{H}/n/201"
    assert it.snippet == "Closing date: 4 Dec 2026. Supply of..."
    assert it.listed_published == "2026-11-20T08:00:00"
    assert it.extra["site_name"] == "Notices Example"
    assert it.extra["extra_snippets"] == "Lot 1: refrigerated trucks … Lot 2: dry"

    reqs = web.requests
    assert len(reqs) == 2  # no robots.txt for the keyed API
    q = reqs[0].url.params
    assert q["q"] == f"tender logistics site:{H}"
    assert q["freshness"] == "pw" and q["count"] == "10"
    assert reqs[0].headers["x-subscription-token"] == "k-123"
    assert reqs[0].headers["user-agent"].startswith("BlackkiteBot/0.1")
    assert clock.sleeps == [pytest.approx(1.1)]  # at most ~1 request per second


def test_search_query_without_key_never_calls_out():
    web = brave_web()
    for key in (None, SecretStr("")):
        with pytest.raises(CollectorError, match="no search key configured"):
            build_collector("search_query", make_client(web), brave_api_key=key).fetch(
                source("search_query", SEARCH_CONFIG)
            )
    assert web.requests == []


def test_search_query_multiple_domains_and_freshness_buckets():
    from blackkite.collectors.search_query import SearchQueryConfig

    cfg = SearchQueryConfig(
        queries=["x"], domains=["a.example", "b.example"], recency_days=30
    )
    assert cfg.query_text("x") == "x (site:a.example OR site:b.example)"
    assert cfg.freshness() == "pm"
    assert SearchQueryConfig(queries=["x"], recency_days=1).freshness() == "pd"
    assert SearchQueryConfig(queries=["x"], recency_days=200).freshness() == "py"
    assert SearchQueryConfig(queries=["x"]).freshness() is None
    assert cfg.host_allowed("www.a.example") and not cfg.host_allowed("ba.example")


def test_search_query_api_error_is_collector_error():
    web = FakeWeb()
    web.add(
        BRAVE, "/res/v1/web/search", httpx.Response(429, json={"type": "ErrorResponse"})
    )
    with pytest.raises(CollectorError, match="HTTP 429"):
        build_collector(
            "search_query", make_client(web), brave_api_key=SecretStr("k")
        ).fetch(source("search_query", SEARCH_CONFIG))
    assert len(web.requests) == 1  # 4xx never retried


def test_search_query_odd_json_shape_yields_nothing():
    web = FakeWeb()
    web.add(
        BRAVE, "/res/v1/web/search", httpx.Response(200, content=json.dumps([1, 2]))
    )
    items = build_collector(
        "search_query", make_client(web), brave_api_key=SecretStr("k")
    ).fetch(source("search_query", {"queries": ["x"]}))
    assert items == []


@pytest.mark.parametrize(
    "config",
    [
        {"queries": []},
        {"queries": ["x"], "domains": ["http://a.example"]},
        {"queries": ["x"], "domains": ["127.0.0.1"]},
        {"queries": ["x"], "recency_days": 0},
        {"queries": ["x"], "count": 50},
        {"queries": ["x"], "api_key": "smuggled"},
    ],
)
def test_search_query_bad_config(config):
    with pytest.raises(ValueError):
        validate_config("search_query", config)


# --- registry ------------------------------------------------------------------------


def test_every_collector_type_is_implemented():
    assert set(registry.IMPLEMENTED) == set(COLLECTOR_TYPES)
    for ctype in COLLECTOR_TYPES:
        c = build_collector(ctype, make_client(FakeWeb()))
        assert callable(c.fetch)
        with pytest.raises(ValueError):
            validate_config(ctype, {"anything": 1})


def test_validate_config_limits():
    with pytest.raises(TypeError, match="JSON object"):
        validate_config("html_list", [1])
    with pytest.raises(ValueError, match="larger"):
        validate_config("html_list", {"x": "y" * 30_000})
    with pytest.raises(CollectorError, match="unknown"):
        build_collector("ftp", make_client(FakeWeb()))
    with pytest.raises(ValueError, match="'ftp' is not a collector type"):
        validate_config("ftp", {})
