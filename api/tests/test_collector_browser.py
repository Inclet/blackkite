"""browser_list collector.

Most tests use a fake renderer. The tests marked ``real_browser`` start headless
Chromium (preinstalled; nothing is downloaded) against a server on 127.0.0.1,
reachable only through ``LoopbackOnlyGuard``, a test-only guard defined here.
The production ``RequestGuard`` blocks loopback, which is tested too. No request
leaves this machine.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from blackkite.collectors import browser_list as bl
from blackkite.collectors.base import CollectorError
from blackkite.collectors.http import RobotsDisallowed
from blackkite.collectors.registry import build_collector, validate_config
from blackkite.db.models import Source
from blackkite.sources.urlsafety import UnsafeURL
from tests.fakes import FakeClock, FakeWeb, make_client

H = "app.example"
CONFIG = {
    "list_url": f"https://{H}/tenders",
    "pagination_pattern": f"https://{H}/tenders?page={{page}}",
    "max_pages": 2,
    "wait_for": "li.notice",
    "selectors": {"item": "li.notice", "title": "a", "deadline": ".dl"},
    "detail": {"selectors": {"organisation": ".buyer"}, "max_items": 5},
}
LIST = """<ul>
<li class="notice"><a href="/n/1">Cold chain services</a><span class="dl">1 Dec 2026</span></li>
<li class="notice"><a href="/n/2">Last-mile distribution</a></li>
</ul>"""
DETAIL = '<div class="buyer">Ministry of Examples</div>'


def source(config=CONFIG) -> Source:
    return Source(
        id=uuid.uuid4(),
        name="JS app",
        home_url=f"https://{H}",
        streams=["tender"],
        kind="original",
        collector_type="browser_list",
        config=config,
        rate_limit=3.0,
    )


class FakeRenderer:
    def __init__(self, pages: dict[str, str]):
        self.pages = pages
        self.calls: list[tuple[str, str | None]] = []
        self.closed = False

    def render(self, url, *, wait_for=None):
        self.calls.append((url, wait_for))
        if url not in self.pages:
            raise CollectorError(f"cannot load {url}")
        return bl.RenderedPage(url=url, html=self.pages[url])

    def close(self):
        self.closed = True


def fake_pages():
    return {
        f"https://{H}/tenders": LIST,
        f"https://{H}/tenders?page=2": "<ul></ul>",
        f"https://{H}/n/1": DETAIL,
    }


def test_renders_pages_parses_like_html_list_and_closes():
    web, clock = FakeWeb(), FakeClock()
    r = FakeRenderer(fake_pages())
    c = build_collector(
        "browser_list", make_client(web, clock), renderer_factory=lambda _: r
    )
    items = c.fetch(source())
    assert [(i.url, i.title) for i in items] == [
        (f"https://{H}/n/1", "Cold chain services"),
        (f"https://{H}/n/2", "Last-mile distribution"),
    ]
    assert items[0].listed_deadline == "1 Dec 2026"
    assert items[0].organisation == "Ministry of Examples"  # from the detail page
    assert "detail_error" in items[1].extra
    assert r.calls == [
        (f"https://{H}/tenders", "li.notice"),
        (f"https://{H}/tenders?page=2", "li.notice"),
        (f"https://{H}/n/1", None),
        (f"https://{H}/n/2", None),
    ]
    assert r.closed
    # robots.txt fetched once through the client; nothing else over plain HTTP.
    assert web.paths() == ["/robots.txt"]
    # The source's per-host delay is kept between top-level renders.
    assert clock.sleeps and all(s == pytest.approx(3.0) for s in clock.sleeps)
    assert len(clock.sleeps) == 4


def test_preview_renders_first_page_and_few_details():
    r = FakeRenderer(fake_pages())
    c = build_collector(
        "browser_list",
        make_client(FakeWeb()),
        renderer_factory=lambda _: r,
        preview=True,
    )
    c.fetch(source())
    assert [u for u, _ in r.calls] == [
        f"https://{H}/tenders",
        f"https://{H}/n/1",
        f"https://{H}/n/2",
    ]


def test_robots_disallow_stops_before_rendering():
    web = FakeWeb()
    web.add(
        H, "/robots.txt", httpx.Response(200, text="User-agent: *\nDisallow: /tenders")
    )
    r = FakeRenderer(fake_pages())
    c = build_collector("browser_list", make_client(web), renderer_factory=lambda _: r)
    with pytest.raises(RobotsDisallowed):
        c.fetch(source())
    assert r.calls == []


def test_render_failure_is_a_collector_error_and_renderer_closed():
    r = FakeRenderer({})
    c = build_collector(
        "browser_list", make_client(FakeWeb()), renderer_factory=lambda _: r
    )
    with pytest.raises(CollectorError, match="cannot load"):
        c.fetch(source())
    assert r.closed


@pytest.mark.parametrize(
    "config",
    [
        {**CONFIG, "wait_for": "li[["},
        {**CONFIG, "list_url": "http://127.0.0.1/"},
        {**CONFIG, "browser_args": ["--no-sandbox"]},
        {**CONFIG, "placeholder": True},
    ],
)
def test_bad_config_rejected(config):
    with pytest.raises(ValueError):
        validate_config("browser_list", config)


def test_config_normalised():
    cfg = validate_config("browser_list", CONFIG)
    assert cfg["wait_for"] == "li.notice" and cfg["first_page"] == 2


# --- the route handler with the production guard (no browser needed) ----------------------


class FakeRequest:
    def __init__(self, url, resource_type="fetch", method="GET"):
        self.url = url
        self.resource_type = resource_type
        self.method = method
        self.post_data_buffer = None

    def all_headers(self):
        return {"accept": "*/*", "user-agent": "HeadlessChrome", "cookie": "a=1"}


class FakeRoute:
    def __init__(self, request):
        self.request = request
        self.result = None

    def abort(self, reason="failed"):
        self.result = ("abort", reason)

    def fulfill(self, *, status, headers, body):
        self.result = ("fulfill", status, headers, body)


@pytest.fixture
def production_guard(monkeypatch):
    monkeypatch.setattr(bl, "_GUARD", bl.RequestGuard())


def handle(url, transport, limits=None, **req):
    route = FakeRoute(FakeRequest(url, **req))
    limits = limits or bl.RenderLimits()
    budget = bl._Budget(deadline=time.monotonic() + 30, limits=limits)
    with httpx.Client(transport=transport) as http:
        bl._fetch_for_browser(http, route, budget, "BlackkiteBot/0.1 (+x)")
    return route.result, budget


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/",
        "http://localhost/",
        "http://10.0.0.1/secret",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://files.example/x",
    ],
)
def test_production_guard_blocks_internal_requests(production_guard, url):
    sent = []
    result, budget = handle(url, httpx.MockTransport(lambda r: sent.append(r)))
    assert result == ("abort", "blockedbyclient")
    assert sent == [] and budget.blocked == [url]


def test_production_guard_blocks_names_resolving_internal(
    production_guard, monkeypatch
):
    from blackkite.sources import urlsafety

    monkeypatch.setattr(urlsafety, "system_resolver", lambda h, p: ["10.1.2.3"])
    monkeypatch.setattr(bl, "system_resolver", lambda h, p: ["10.1.2.3"])
    sent = []
    inner = httpx.MockTransport(lambda r: sent.append(r))
    transport = urlsafety.GuardedTransport(inner, lambda h, p: ["10.1.2.3"])
    result, _ = handle("https://rebind.example/x", transport)
    assert result == ("abort", "blockedbyclient") and sent == []


def test_route_fulfils_public_requests_with_our_user_agent(production_guard):
    seen = []

    def app(req):
        seen.append(req)
        return httpx.Response(200, json={"ok": True}, headers={"set-cookie": "s=1"})

    from blackkite.sources.urlsafety import GuardedTransport
    from tests.fakes import public_resolver

    transport = GuardedTransport(httpx.MockTransport(app), public_resolver)
    result, budget = handle(f"https://{H}/api/items", transport)
    assert result[0] == "fulfill" and result[1] == 200
    assert json.loads(result[3]) == {"ok": True}
    assert seen[0].headers["user-agent"] == "BlackkiteBot/0.1 (+x)"
    assert seen[0].headers["cookie"] == "a=1"
    assert budget.requests == 1


def test_route_refuses_images_methods_downloads_and_oversize(production_guard):
    from blackkite.sources.urlsafety import GuardedTransport
    from tests.fakes import public_resolver

    def app(req):
        if req.url.path == "/file":
            return httpx.Response(
                200, content=b"PDF", headers={"content-disposition": "attachment"}
            )
        return httpx.Response(200, content=b"x" * 5000)

    t = GuardedTransport(httpx.MockTransport(app), public_resolver)
    assert handle(f"https://{H}/a.png", t, resource_type="image")[0][0] == "abort"
    assert handle(f"https://{H}/x", t, method="DELETE")[0][0] == "abort"
    assert handle(f"https://{H}/file", t)[0] == ("abort", "blockedbyclient")
    small = bl.RenderLimits(max_bytes=1000)
    assert handle(f"https://{H}/big", t, limits=small)[0] == ("abort", "failed")
    one = bl.RenderLimits(max_requests=0)
    assert handle(f"https://{H}/big", t, limits=one)[0] == ("abort", "timedout")


def test_renderer_refuses_internal_top_level_urls_before_starting():
    r = bl.PlaywrightRenderer("BlackkiteBot/0.1 (+x)")
    with pytest.raises(UnsafeURL):
        r.render("http://127.0.0.1:9000/")
    assert r._proc is None


# --- real Chromium, local server, test-only guard ---------------------------------------------


def _chromium_installed() -> bool:
    root = Path(
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH", Path.home() / ".cache/ms-playwright")
    )
    return any(root.glob("chromium_headless_shell-*/INSTALLATION_COMPLETE")) or any(
        root.glob("chromium-*/INSTALLATION_COMPLETE")
    )


real_browser = pytest.mark.skipif(
    not _chromium_installed(), reason="headless Chromium not installed"
)


class LoopbackOnlyGuard(bl.RequestGuard):
    """TEST ONLY. Allows exactly http://127.0.0.1:<port>, nothing else; production
    code never constructs it."""

    def __init__(self, port: int) -> None:
        self.port = port

    def check(self, url: str) -> None:
        p = urlsplit(url)
        if p.scheme != "http" or p.hostname != "127.0.0.1" or p.port != self.port:
            raise UnsafeURL(f"test guard: {url} is not the local test server")

    def transport(self) -> httpx.BaseTransport:
        return httpx.HTTPTransport(retries=0)


PAGES = {
    "/list": """<!doctype html><html><body><ul id="list"></ul>
<img src="http://169.254.169.254/latest/meta-data/">
<script>
  alert("dialogs are dismissed");
  window.open("/popup");
  fetch("http://10.0.0.1/secret").catch(() => {});
  fetch("http://127.0.0.1:1/other-port").catch(() => {});
  fetch("/api/items").then(r => r.json()).then(items => {
    const ul = document.getElementById("list");
    for (const it of items) {
      const li = document.createElement("li");
      li.className = "notice";
      li.innerHTML = `<a href="${it.url}">${it.title}</a>`;
      ul.appendChild(li);
    }
  });
</script></body></html>""",
    "/api/items": json.dumps(
        [
            {"title": "Rendered notice one", "url": "/n/1"},
            {"title": "Rendered two", "url": "/n/2"},
        ]
    ),
    "/spin": "<html><body><script>while (true) {}</script></body></html>",
    "/plain": "<html><body><p id='p'>static</p></body></html>",
}


@pytest.fixture
def local_server():
    hits: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/plain")
                self.end_headers()
                return
            if self.path == "/download":
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", "attachment; filename=x.pdf")
                self.end_headers()
                self.wfile.write(b"%PDF-1.4")
                return
            body = PAGES.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            data = body.encode()
            self.send_response(200)
            ctype = "application/json" if self.path.startswith("/api") else "text/html"
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1], hits
    server.shutdown()


@real_browser
def test_real_browser_renders_js_list_through_the_guard(local_server):
    port, hits = local_server
    base = f"http://127.0.0.1:{port}"
    r = bl.PlaywrightRenderer(
        "BlackkiteBot/0.1 (+test)",
        bl.RenderLimits(timeout_seconds=20),
        guard=LoopbackOnlyGuard(port),
    )
    try:
        page = r.render(f"{base}/list", wait_for="li.notice")
        assert "Rendered notice one" in page.html and "Rendered two" in page.html
        assert page.url == f"{base}/list"
        assert "http://10.0.0.1/secret" in page.blocked
        assert "http://127.0.0.1:1/other-port" in page.blocked
        assert "/api/items" in hits
        # Redirects are followed through the route.
        page = r.render(f"{base}/redirect")
        assert page.url == f"{base}/plain" and "static" in page.html
        # Downloads are refused.
        with pytest.raises(CollectorError):
            r.render(f"{base}/download")
        # A missing wait_for selector is reported.
        with pytest.raises(CollectorError, match="did not appear"):
            bl.PlaywrightRenderer(
                "ua", bl.RenderLimits(timeout_seconds=2), guard=LoopbackOnlyGuard(port)
            ).render(f"{base}/plain", wait_for="li.never")
    finally:
        r.close()
    assert r._proc is None
    assert bl.tagged_pids(r.tag) == []


@real_browser
def test_real_browser_hard_timeout_kills_the_browser(local_server):
    port, _ = local_server
    r = bl.PlaywrightRenderer(
        "ua", bl.RenderLimits(timeout_seconds=2), guard=LoopbackOnlyGuard(port)
    )
    started = time.monotonic()
    try:
        with pytest.raises(CollectorError):
            r.render(f"http://127.0.0.1:{port}/spin")
    finally:
        r.close()
    assert time.monotonic() - started < 40
    assert bl.tagged_pids(r.tag) == []  # driver and Chromium killed too


@real_browser
def test_real_browser_with_production_guard_cannot_reach_loopback(local_server):
    """The production guard inside the browser process: a page on 127.0.0.1 is
    not loaded even when the parent-side check is skipped."""
    port, hits = local_server
    r = bl.PlaywrightRenderer("ua", bl.RenderLimits(timeout_seconds=10))
    try:
        with pytest.raises(CollectorError, match="blocked"):
            r._render_in_child(f"http://127.0.0.1:{port}/plain", None)
    finally:
        r.close()
    assert hits == []
    assert bl.tagged_pids(r.tag) == []


@real_browser
def test_real_browser_flags_alone_block_loopback_and_ip_literals(
    local_server, monkeypatch
):
    """The backstop under the route: Chromium launched as the renderer launches
    it, with no route at all, reaches nothing. Loopback is not exempt from the
    dead proxy even when Playwright is told to stop forcing that, and the
    resolver rule refuses IP literals as well as names."""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    assert "--proxy-bypass-list=<-loopback>" in bl.CHROMIUM_ARGS
    port, hits = local_server
    monkeypatch.setenv("PLAYWRIGHT_DISABLE_FORCED_CHROMIUM_PROXIED_LOOPBACK", "1")
    urls = [
        f"http://127.0.0.1:{port}/plain",
        f"http://localhost:{port}/plain",
        f"http://2130706433:{port}/plain",  # 127.0.0.1 as one number
        f"http://[::1]:{port}/plain",
    ]
    resolver_only = [a for a in bl.CHROMIUM_ARGS if not a.startswith("--proxy")]
    proxy_only = [a for a in bl.CHROMIUM_ARGS if not a.startswith("--host-resolver")]
    # bypass "<loopback>" asks Playwright to let loopback skip the proxy; our
    # flag, after Playwright's, overrides it.
    leaky_proxy = {"server": bl.DEAD_PROXY, "bypass": "<loopback>"}
    with sync_playwright() as p:
        for launch in (
            {"args": bl.CHROMIUM_ARGS, "proxy": leaky_proxy},  # as the renderer
            {"args": proxy_only, "proxy": leaky_proxy},  # the proxy flag alone
            {"args": resolver_only},  # no proxy: the resolver rule alone
        ):
            browser = p.chromium.launch(headless=True, **launch)
            try:
                page = browser.new_page()
                for url in urls:
                    with pytest.raises(PlaywrightError, match="net::ERR_"):
                        page.goto(url, timeout=5000)
            finally:
                browser.close()
    assert hits == []
