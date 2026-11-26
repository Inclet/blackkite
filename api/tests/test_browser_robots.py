"""Decision 48: in browser_list rendering, robots.txt is checked for every
main-frame navigation (the requested page, each redirect target, script
navigations), not only the URL the collector asked for. A disallowed page is
stopped and recorded.

Unit tests drive the route handler with fake requests and a fake robots.txt
(MockTransport); the ``real_browser`` tests use headless Chromium against a
server on 127.0.0.1 through the test-only loopback guard. Nothing leaves this
machine.
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from blackkite.collectors import browser_list as bl
from blackkite.collectors.http import RobotsDisallowed
from blackkite.sources.urlsafety import GuardedTransport
from tests.fakes import public_resolver
from tests.test_collector_browser import (
    FakeRequest,
    FakeRoute,
    LoopbackOnlyGuard,
    real_browser,
)

H = "app.example"
ROBOTS = "User-agent: *\nDisallow: /private\nCrawl-delay: 7\n"


class _Frame:
    parent_frame = None


class NavRequest(FakeRequest):
    """A main-frame navigation request."""

    def __init__(self, url):
        super().__init__(url, resource_type="document")
        self.frame = _Frame()

    def is_navigation_request(self):
        return True


@pytest.fixture(autouse=True)
def fresh_robots(monkeypatch):
    monkeypatch.setattr(bl, "_ROBOTS", {})
    monkeypatch.setattr(bl, "_GUARD", bl.RequestGuard())


def site(robots_status=200, robots=ROBOTS):
    sent: list[str] = []

    def app(req: httpx.Request) -> httpx.Response:
        sent.append(req.url.path)
        if req.url.path == "/robots.txt":
            return httpx.Response(robots_status, text=robots)
        if req.url.path == "/go":
            return httpx.Response(302, headers={"location": "/private/x"})
        return httpx.Response(200, text="<p>page</p>")

    return GuardedTransport(httpx.MockTransport(app), public_resolver), sent


def navigate(url, transport):
    route = FakeRoute(NavRequest(url))
    budget = bl._Budget(deadline=time.monotonic() + 30, limits=bl.RenderLimits())
    with httpx.Client(transport=transport) as http:
        bl._fetch_for_browser(http, route, budget, "BlackkiteBot/0.1 (+x)")
    return route.result, budget


def test_disallowed_main_navigation_is_stopped_and_recorded():
    t, sent = site()
    result, budget = navigate(f"https://{H}/private/notice", t)
    assert result == ("abort", "aborted")
    assert budget.robots_blocked == f"https://{H}/private/notice"
    assert sent == ["/robots.txt"]  # the page itself was never requested
    assert budget.log[-1]["outcome"] == "robots"
    assert budget.crawl_delays == {H: 7.0}


def test_allowed_main_navigation_is_fetched():
    t, sent = site()
    result, budget = navigate(f"https://{H}/tenders", t)
    assert result[0] == "fulfill" and result[1] == 200
    assert sent == ["/robots.txt", "/tenders"]
    assert budget.robots_blocked is None
    assert budget.log[-1] == {
        "url": f"https://{H}/tenders",
        "method": "GET",
        "type": "document",
        "outcome": "fulfilled",
        "status": 200,
    }


def test_redirect_target_is_handed_back_and_checked_on_its_own_navigation():
    t, sent = site()
    result, budget = navigate(f"https://{H}/go", t)
    # The redirect is not followed here: _render_one navigates to the target,
    # which comes back through the route as a new main-frame navigation.
    assert result == ("abort", "aborted")
    assert budget.redirect_to == f"https://{H}/private/x"
    result, budget = navigate(budget.redirect_to, t)
    assert result == ("abort", "aborted")
    assert budget.robots_blocked == f"https://{H}/private/x"
    assert "/private/x" not in sent
    assert sent.count("/robots.txt") == 1  # cached per origin


def test_robots_unreachable_disallows_everything():
    t, sent = site(robots_status=503)
    result, budget = navigate(f"https://{H}/tenders", t)
    assert result == ("abort", "aborted")
    assert budget.robots_blocked and "/tenders" not in sent


def test_robots_missing_allows():
    t, sent = site(robots_status=404)
    result, _ = navigate(f"https://{H}/private/x", t)
    assert result[0] == "fulfill" and sent == ["/robots.txt", "/private/x"]


def test_unsafe_navigation_is_blocked_not_a_robots_case():
    t, sent = site()
    result, budget = navigate("http://10.0.0.1/", t)
    assert result == ("abort", "blockedbyclient")
    assert budget.robots_blocked is None and budget.blocked == ["http://10.0.0.1/"]
    assert sent == []


def test_subresources_are_not_robots_checked():
    """Decision 48 covers pages (main-frame navigations); scripts and XHR a
    page loads are not pages."""
    t, sent = site()
    route = FakeRoute(FakeRequest(f"https://{H}/private/api", resource_type="fetch"))
    budget = bl._Budget(deadline=time.monotonic() + 30, limits=bl.RenderLimits())
    with httpx.Client(transport=t) as http:
        bl._fetch_for_browser(http, route, budget, "ua")
    assert route.result[0] == "fulfill" and sent == ["/private/api"]


# --- real Chromium ----------------------------------------------------------------------

PAGES = {
    "/robots.txt": ROBOTS,
    "/open": "<html><body><p id='p'>open page</p></body></html>",
    "/private/page": "<html><body>secret</body></html>",
    "/jump": """<html><body><p id='p'>before</p>
<script>setTimeout(() => { location.href = "/private/page"; }, 50);</script>
</body></html>""",
}


@pytest.fixture
def robots_server():
    hits: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            if self.path == "/to-private":
                self.send_response(302)
                self.send_header("Location", "/private/page")
                self.end_headers()
                return
            body = PAGES.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            data = body.encode()
            self.send_response(200)
            ctype = "text/plain" if self.path == "/robots.txt" else "text/html"
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], hits
    server.shutdown()


@real_browser
def test_real_browser_checks_robots_on_redirects_and_script_navigation(
    robots_server,
):
    port, hits = robots_server
    base = f"http://127.0.0.1:{port}"
    r = bl.PlaywrightRenderer(
        "BlackkiteBot/0.1 (+test)",
        bl.RenderLimits(timeout_seconds=20),
        guard=LoopbackOnlyGuard(port),
    )
    try:
        # The requested page itself.
        with pytest.raises(RobotsDisallowed, match="robots.txt disallows"):
            r.render(f"{base}/private/page")
        # A redirect target: stopped, and the error says where it came from.
        with pytest.raises(RobotsDisallowed) as e:
            r.render(f"{base}/to-private")
        assert f"{base}/private/page" in str(e.value)
        assert f"reached from {base}/to-private" in str(e.value)
        assert any(
            x["outcome"] == "robots" and x["url"] == f"{base}/private/page"
            for x in r.last_request_log
        )
        # A script navigation: stopped; the allowed page is what we read.
        page = r.render(f"{base}/jump")
        assert page.url == f"{base}/jump" and "before" in page.html
        assert any(x["outcome"] == "robots" for x in page.request_log)
        assert r.last_crawl_delays == {"127.0.0.1": 7.0}
        # An allowed page renders as before.
        assert "open page" in r.render(f"{base}/open").html
    finally:
        r.close()
    assert "/private/page" not in hits
    assert hits.count("/robots.txt") == 1  # cached in the browser process
    assert bl.tagged_pids(r.tag) == []
