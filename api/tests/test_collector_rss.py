"""rss collector: RSS 2.0, RSS 1.0 and Atom, through the guarded client. Offline;
feeds are synthetic files under tests/data/feeds."""

import uuid
from pathlib import Path

import httpx
import pytest

from blackkite.collectors.base import CollectorError
from blackkite.collectors.http import RobotsDisallowed
from blackkite.collectors.registry import build_collector, validate_config
from blackkite.db.models import Source
from tests.fakes import FakeWeb, make_client

FEEDS = Path(__file__).parent / "data" / "feeds"
H = "news.example"


def source(config, rate_limit=2.0) -> Source:
    return Source(
        id=uuid.uuid4(),
        name="Feed",
        home_url=f"https://{H}",
        streams=["funding"],
        kind="news",
        collector_type="rss",
        config=config,
        rate_limit=rate_limit,
    )


def serve(web: FakeWeb, host: str, path: str, name: str, ctype="application/rss+xml"):
    web.add(
        host,
        path,
        httpx.Response(
            200, content=(FEEDS / name).read_bytes(), headers={"content-type": ctype}
        ),
    )


def collect(web, config, **kw):
    return build_collector("rss", make_client(web), **kw).fetch(source(config))


def test_rss2_items():
    web = FakeWeb()
    serve(web, H, "/feed", "rss2.xml")
    items = collect(web, {"feed_url": f"https://{H}/feed"})
    by_url = {i.url: i for i in items}
    assert list(by_url) == [
        f"https://{H}/2026/11/accelerator",
        f"https://{H}/2026/11/bond",
        f"https://{H}/2026/11/relative",
        f"https://{H}/2026/11/summit",
    ]
    a = by_url[f"https://{H}/2026/11/accelerator"]
    assert a.title == "Call for applications: agri-food accelerator & grant"
    assert a.listed_published == "2026-11-24T10:00:00+00:00"
    assert a.snippet == "Applications close 15 December 2026."
    assert a.organisation is None  # a journalist is not the issuer
    assert a.extra == {
        "author": "A. Reporter",
        "feed_title": "Example Business News",
        "categories": "Funding",
    }
    b = by_url[f"https://{H}/2026/11/bond"]
    assert b.listed_published == "25 Nov 2026"  # left for the validate stage
    assert b.snippet == "Ten-year bond, auction on 2 December."
    assert b.extra["author"] == "Markets Desk"
    s = by_url[f"https://{H}/2026/11/summit"]
    assert s.title.startswith("Summit on logistics in Kigali")  # from description
    assert web.paths() == ["/robots.txt", "/feed"]


def test_author_as_organisation_for_issuer_feeds():
    web = FakeWeb()
    serve(web, "issuer.example", "/feed", "atom.xml", "application/atom+xml")
    items = collect(
        web,
        {"feed_url": "https://issuer.example/feed", "author_as_organisation": True},
    )
    assert [i.url for i in items] == [
        "https://issuer.example/notices/1",
        "https://issuer.example/notices/2",
    ]
    first, second = items
    assert first.title == "EOI: cold chain logistics"
    assert first.organisation == "Example Issuer Ltd"
    assert first.listed_published == "2026-11-20T08:00:00Z"
    assert first.snippet == "Deadline 10 Dec 2026."
    assert first.extra["categories"] == "tender"
    assert second.listed_published == "2026-11-22T08:00:00Z"  # updated, no published
    assert second.snippet == "Full text here."
    assert second.organisation is None


def test_rss1_rdf_feed():
    web = FakeWeb()
    serve(web, "old.example", "/rdf", "rss1.xml")
    (item,) = collect(web, {"feed_url": "https://old.example/rdf"})
    assert item.url == "https://old.example/a"
    assert item.listed_published == "2026-11-23"
    assert item.extra["feed_title"] == "Old Feed"


def test_max_items_and_preview_limit():
    web = FakeWeb()
    serve(web, H, "/feed", "rss2.xml")
    items = collect(web, {"feed_url": f"https://{H}/feed", "max_items": 2})
    assert len(items) == 2
    many = "".join(
        f"<item><title>T{i}</title><link>https://{H}/{i}</link></item>"
        for i in range(60)
    )
    web.add(
        H,
        "/big",
        httpx.Response(200, text=f"<rss><channel>{many}</channel></rss>"),
    )
    cfg = {"feed_url": f"https://{H}/big", "max_items": 200}
    assert len(collect(web, cfg)) == 60
    assert len(collect(web, cfg, preview=True)) == 20


@pytest.mark.parametrize(
    "body, match",
    [
        (
            (
                '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">'
                '<!ENTITY b "&a;&a;&a;">]><rss><channel><title>&b;</title></channel></rss>'
            ),
            "EntitiesForbidden",
        ),
        (
            (
                '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
                "<rss><channel><title>&x;</title></channel></rss>"
            ),
            "refused",
        ),
        ("<html><body>not a feed</body></html>", "not an RSS or Atom feed"),
        ("<rss><channel><item>", "not well-formed"),
        ("<rss version='2.0'></rss>", "no <channel>"),
    ],
)
def test_hostile_or_broken_feeds_fail_cleanly(body, match):
    web = FakeWeb()
    web.add(H, "/feed", httpx.Response(200, text=body))
    with pytest.raises(CollectorError, match=match):
        collect(web, {"feed_url": f"https://{H}/feed"})


def test_feed_goes_through_robots_and_guard():
    web = FakeWeb()
    web.add(H, "/robots.txt", httpx.Response(200, text="User-agent: *\nDisallow: /"))
    serve(web, H, "/feed", "rss2.xml")
    with pytest.raises(RobotsDisallowed):
        collect(web, {"feed_url": f"https://{H}/feed"})
    assert web.paths() == ["/robots.txt"]


@pytest.mark.parametrize(
    "config",
    [
        {"feed_url": "http://127.0.0.1/feed"},
        {"feed_url": "file:///etc/passwd"},
        {"feed_url": f"https://{H}/feed", "max_items": 0},
        {"feed_url": f"https://{H}/feed", "module": "os"},
        {},
        {"placeholder": True},
    ],
)
def test_bad_config_rejected(config):
    with pytest.raises(ValueError):
        validate_config("rss", config)


def test_config_normalised():
    assert validate_config("rss", {"feed_url": f"https://{H}/feed"}) == {
        "feed_url": f"https://{H}/feed",
        "max_items": 50,
        "author_as_organisation": False,
    }
