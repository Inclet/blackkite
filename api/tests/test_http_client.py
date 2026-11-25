"""Collector HTTP client: UA, robots, delay, conditional GET, retry, limits. Offline."""

import httpx
import pytest

from blackkite.collectors.base import CollectorError
from blackkite.collectors.http import (
    DbHttpCache,
    FetchError,
    ResponseTooLarge,
    RobotsDisallowed,
)
from blackkite.config import Settings, user_agent
from blackkite.sources.urlsafety import UnsafeURL
from tests.fakes import FakeClock, FakeWeb, make_client

H = "site.example"


def test_user_agent_names_the_bot_and_contact():
    s = Settings(bot_contact_url="https://example.com/bot", _env_file=None)
    assert user_agent(s) == "BlackkiteBot/0.1 (+https://example.com/bot)"


def test_sends_honest_user_agent_and_checks_robots_first():
    web = FakeWeb()
    web.html(H, "/list", "<p>hi</p>")
    c = make_client(web)
    r = c.get(f"https://{H}/list")
    assert r.text == "<p>hi</p>"
    assert web.paths() == ["/robots.txt", "/list"]
    assert all(
        q.headers["user-agent"] == "BlackkiteBot/0.1 (+https://example.com/bot)"
        for q in web.requests
    )


def test_robots_disallow_is_obeyed_and_cached_per_host():
    web = FakeWeb()
    web.add(
        H,
        "/robots.txt",
        httpx.Response(200, text="User-agent: *\nDisallow: /private\n"),
    )
    web.html(H, "/public", "ok")
    c = make_client(web)
    c.get(f"https://{H}/public")
    with pytest.raises(RobotsDisallowed):
        c.get(f"https://{H}/private/x")
    c.get(f"https://{H}/public")
    assert web.paths().count("/robots.txt") == 1
    assert "/private/x" not in web.paths()


def test_robots_rules_for_our_token():
    web = FakeWeb()
    web.add(
        H,
        "/robots.txt",
        httpx.Response(200, text="User-agent: BlackkiteBot\nDisallow: /\n"),
    )
    with pytest.raises(RobotsDisallowed):
        make_client(web).get(f"https://{H}/anything")


def test_robots_unreachable_means_disallow_all():
    web = FakeWeb()
    web.add(H, "/robots.txt", httpx.Response(503))
    web.html(H, "/list", "x")
    with pytest.raises(RobotsDisallowed):
        make_client(web).get(f"https://{H}/list")


def test_robots_crawl_delay_raises_host_delay():
    web = FakeWeb()
    web.add(
        H, "/robots.txt", httpx.Response(200, text="User-agent: *\nCrawl-delay: 30\n")
    )
    web.html(H, "/a", "a")
    web.html(H, "/b", "b")
    clock = FakeClock()
    c = make_client(web, clock)
    c.get(f"https://{H}/a", delay=2)
    c.get(f"https://{H}/b", delay=2)
    # Crawl-delay (30) beats the source's 2 s, from the request after robots.txt on.
    assert clock.sleeps == [30, 30]


def test_per_host_delay_between_requests():
    web = FakeWeb()
    web.html(H, "/a", "a")
    web.html(H, "/b", "b")
    web.html("other.example", "/c", "c")
    clock = FakeClock()
    c = make_client(web, clock)
    c.get(f"https://{H}/a", delay=10)  # robots, then a
    c.get("https://other.example/c", delay=10)  # other host: robots then c
    c.get(f"https://{H}/b", delay=10)
    # b: 20 s have passed since a (the wait for c counted), so no further sleep.
    assert clock.sleeps == [10, 10]


def test_conditional_get_uses_etag_and_returns_cached_body():
    web = FakeWeb()
    seen = []

    def page(req: httpx.Request):
        seen.append(dict(req.headers))
        if req.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(
            200,
            text="<p>v1</p>",
            headers={
                "etag": '"v1"',
                "last-modified": "Mon, 23 Nov 2026 10:00:00 GMT",
                "content-type": "text/html",
            },
        )

    web.add(H, "/list", page)
    c = make_client(web)
    first = c.get(f"https://{H}/list")
    second = c.get(f"https://{H}/list")
    assert not first.from_cache and second.from_cache
    assert second.text == "<p>v1</p>" and second.status == 200
    assert seen[1]["if-none-match"] == '"v1"'
    assert seen[1]["if-modified-since"] == "Mon, 23 Nov 2026 10:00:00 GMT"


def test_db_cache_round_trip(Sessions):
    from blackkite.collectors.http import CachedResponse

    cache = DbHttpCache(Sessions)
    assert cache.get("https://a.example/") is None
    cache.put("https://a.example/", CachedResponse('"1"', None, "text/html", b"one"))
    cache.put("https://a.example/", CachedResponse('"2"', None, "text/html", b"two"))
    got = cache.get("https://a.example/")
    assert got is not None and got.etag == '"2"' and got.content == b"two"


def test_retries_once_on_5xx_then_gives_up():
    web = FakeWeb()
    calls = []

    def flaky(req):
        calls.append(1)
        return httpx.Response(502)

    web.add(H, "/list", flaky)
    clock = FakeClock()
    c = make_client(web, clock, retry_backoff=7)
    with pytest.raises(FetchError, match="HTTP 502"):
        c.get(f"https://{H}/list")
    assert len(calls) == 2
    assert 7 in clock.sleeps


def test_retry_on_5xx_can_succeed():
    web = FakeWeb()
    answers = iter([httpx.Response(500), httpx.Response(200, text="ok")])
    web.add(H, "/list", lambda req: next(answers))
    assert make_client(web).get(f"https://{H}/list").text == "ok"


def test_never_retries_4xx():
    web = FakeWeb()
    calls = []

    def gone(req):
        calls.append(1)
        return httpx.Response(429)

    web.add(H, "/list", gone)
    with pytest.raises(FetchError, match="HTTP 429"):
        make_client(web).get(f"https://{H}/list")
    assert len(calls) == 1


def test_retries_once_on_connect_error():
    web = FakeWeb()
    calls = []

    def down(req):
        calls.append(1)
        raise httpx.ConnectError("refused", request=req)

    web.add(H, "/list", down)
    with pytest.raises(FetchError, match="cannot connect"):
        make_client(web).get(f"https://{H}/list")
    assert len(calls) == 2


def test_fetch_errors_are_collector_errors():
    assert issubclass(FetchError, CollectorError)
    assert issubclass(UnsafeURL, CollectorError)


def test_size_limit_declared_and_streamed():
    web = FakeWeb()
    web.add(H, "/big", httpx.Response(200, content=b"x" * 2000))
    web.add(H, "/stream", httpx.Response(200, content=iter([b"x" * 600] * 4)))
    c = make_client(web, max_bytes=1000)
    with pytest.raises(ResponseTooLarge, match="2000 bytes"):
        c.get(f"https://{H}/big")  # Content-Length says too big: refused up front
    with pytest.raises(ResponseTooLarge, match="exceeds"):
        c.get(f"https://{H}/stream")  # no Content-Length: cut off while streaming


def test_redirects_followed_and_each_hop_checked():
    web = FakeWeb()
    web.add(H, "/old", httpx.Response(301, headers={"location": "/new"}))
    web.html(H, "/new", "moved")
    web.add(H, "/evil", httpx.Response(302, headers={"location": "http://10.0.0.1/"}))
    web.add(H, "/loop", httpx.Response(302, headers={"location": "/loop"}))
    c = make_client(web)
    r = c.get(f"https://{H}/old")
    assert r.text == "moved" and r.url == f"https://{H}/new"
    with pytest.raises(UnsafeURL):
        c.get(f"https://{H}/evil")
    with pytest.raises(FetchError, match="too many redirects"):
        c.get(f"https://{H}/loop")


def test_redirect_to_robots_disallowed_path_refused():
    web = FakeWeb()
    web.add(
        H, "/robots.txt", httpx.Response(200, text="User-agent: *\nDisallow: /no\n")
    )
    web.add(H, "/yes", httpx.Response(302, headers={"location": "/no"}))
    with pytest.raises(RobotsDisallowed):
        make_client(web).get(f"https://{H}/yes")
    assert "/no" not in web.paths()


def test_hostname_resolving_private_never_requested():
    web = FakeWeb()
    c = make_client(web, resolver=lambda h, p: ["127.0.0.1"])
    with pytest.raises(UnsafeURL):
        c.get("https://intranet.example/")
    assert web.requests == []
