"""The renderer service (decision 46): refuses to start with secrets in its
environment, authenticates callers with BK_RENDERER_TOKEN, applies its own
guard and limits whatever the caller asks, and ``RemoteRenderer`` talks to it.

Most tests run the service in-process (FastAPI TestClient) with a fake
renderer. The ``real_browser`` tests run it under uvicorn on 127.0.0.1 with
headless Chromium and the test-only loopback guard. Nothing leaves this machine.
"""

from __future__ import annotations

import secrets
import socket
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from blackkite.cli import app as cli_app
from blackkite.collectors import browser_list as bl
from blackkite.collectors.base import CollectorError
from blackkite.collectors.http import RobotsDisallowed
from blackkite.collectors.registry import build_collector
from blackkite.config import Settings
from blackkite.renderer import service as svc
from blackkite.renderer.client import RemoteRenderer
from blackkite.renderer.settings import (
    FORBIDDEN_ENV,
    RendererConfigError,
    RendererSettings,
)
from blackkite.sources.urlsafety import UnsafeURL
from tests.fakes import FakeWeb, make_client
from tests.test_collector_browser import (
    LoopbackOnlyGuard,
    local_server,  # noqa: F401 - fixture
    real_browser,
    source,
)

TOKEN = secrets.token_hex(32)
URL = "https://app.example/tenders"


def settings(**kw) -> RendererSettings:
    return RendererSettings(token=TOKEN, **kw)


class FakeRenderer:
    """Stands in for PlaywrightRenderer inside the service."""

    def __init__(self, ceiling, guard, html="<ul><li>ok</li></ul>", error=None):
        self.ceiling = ceiling
        self.guard = guard
        self.html = html
        self.error = error
        self.calls: list[tuple[str, str | None, bl.RenderLimits]] = []
        self.last_crawl_delays: dict[str, float] = {}
        self.last_request_log: tuple = ()
        self.closed = False
        self.hold: threading.Event | None = None

    def render(self, url, *, wait_for=None, limits=None):
        self.calls.append((url, wait_for, limits))
        self.last_request_log = ({"url": url, "outcome": "fulfilled"},)
        if self.hold is not None:
            self.hold.wait(5)
        if self.error is not None:
            raise self.error
        return bl.RenderedPage(
            url=url, html=self.html, requests=3, request_log=self.last_request_log
        )

    def close(self):
        self.closed = True


class NoPace(svc.HostPacer):
    def __init__(self):
        super().__init__(1.0, 30.0, sleep=lambda s: None)


def service(*, renderer=None, environ=None, pacer=None, **kw):
    made: list[FakeRenderer] = []

    def factory(ceiling, guard):
        r = renderer or FakeRenderer(ceiling, guard)
        made.append(r)
        return r

    app = svc.create_app(
        settings(**kw),
        renderer_factory=factory,
        environ={} if environ is None else environ,
        pacer=pacer or NoPace(),
    )
    return app, made


def auth(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


# --- no secrets -----------------------------------------------------------------------


@pytest.mark.parametrize("name", FORBIDDEN_ENV)
def test_refuses_to_start_with_a_secret_in_its_environment(name):
    value = "postgresql+psycopg://u:hunter2-very-secret@db/x"
    with pytest.raises(RendererConfigError) as e:
        svc.create_app(settings(), environ={name: value, "PATH": "/usr/bin"})
    assert name in str(e.value) and value not in str(e.value)


def test_refuses_even_an_empty_secret_variable():
    with pytest.raises(RendererConfigError, match="ANTHROPIC_API_KEY"):
        svc.create_app(settings(), environ={"ANTHROPIC_API_KEY": ""})


def test_cli_refuses_to_start_with_secrets_or_without_a_token(monkeypatch):
    for name in FORBIDDEN_ENV:
        monkeypatch.delenv(name, raising=False)
    started = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: started.append(a))
    runner = CliRunner()

    monkeypatch.delenv("BK_RENDERER_TOKEN", raising=False)
    r = runner.invoke(cli_app, ["renderer"])
    assert r.exit_code == 2 and "BK_RENDERER_TOKEN" in r.output

    monkeypatch.setenv("BK_RENDERER_TOKEN", "x" * 40)
    r = runner.invoke(cli_app, ["renderer"])
    assert r.exit_code == 2 and "BK_RENDERER_TOKEN" in r.output
    assert "x" * 40 not in r.output

    monkeypatch.setenv("BK_RENDERER_TOKEN", TOKEN)
    monkeypatch.setenv("BRAVE_API_KEY", "brave-key-value-123")
    r = runner.invoke(cli_app, ["renderer"])
    assert r.exit_code == 2 and "BRAVE_API_KEY" in r.output
    assert "brave-key-value-123" not in r.output
    assert started == []

    monkeypatch.delenv("BRAVE_API_KEY")
    r = runner.invoke(cli_app, ["renderer", "--port", "8199"])
    assert r.exit_code == 0, r.output
    assert len(started) == 1


@pytest.mark.parametrize("token", ["change-me", "x" * 40, "short-but-random-Zq8#"])
def test_weak_token_refused(token):
    with pytest.raises(ValidationError, match="BK_RENDERER_TOKEN") as e:
        RendererSettings(token=token)
    assert token not in str(e.value)


def test_renderer_reads_no_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(f"BK_RENDERER_TOKEN={TOKEN}\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BK_RENDERER_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        RendererSettings()


# --- token auth -----------------------------------------------------------------------


def test_render_needs_the_token():
    app, made = service()
    with TestClient(app) as c:
        body = {"url": URL}
        assert c.post("/render", json=body).status_code == 401
        r = c.post("/render", json=body, headers=auth(secrets.token_hex(32)))
        assert r.status_code == 401
        assert r.headers["www-authenticate"] == "Bearer"
        r = c.post("/render", json=body, headers={"Authorization": f"Basic {TOKEN}"})
        assert r.status_code == 401
        r = c.post("/render", json=body, headers={"Authorization": TOKEN})
        assert r.status_code == 401
        assert made == []  # no browser was started for any of them
        r = c.post("/render", json=body, headers=auth())
        assert r.status_code == 200 and r.json()["ok"] is True
        # Health check needs no token and says nothing else.
        assert c.get("/healthz").json() == {"ok": True}
        assert c.get("/docs").status_code == 404
        assert c.get("/openapi.json").status_code == 404


def test_malformed_requests_are_refused():
    app, _ = service()
    with TestClient(app) as c:
        for body in (
            {},
            {"url": URL, "wait_for": "li[["},
            {"url": URL, "user_agent": "Mozilla"},
            {"url": URL, "limits": {"max_bytes": -1}},
            {"url": "https://a.example/" + "x" * 3000},
        ):
            assert c.post("/render", json=body, headers=auth()).status_code == 422


# --- limits and guard on the server side --------------------------------------------


def test_limits_are_clamped_to_the_service_ceilings():
    app, made = service(
        timeout_seconds=10,
        max_bytes=100_000,
        total_bytes=400_000,
        max_requests=20,
        subresource_delay=0.5,
        request_timeout=5,
    )
    greedy = {
        "timeout_seconds": 999,
        "max_bytes": 10**9,
        "total_bytes": 10**10,
        "max_requests": 10**6,
        "subresource_delay": 0,
        "request_timeout": 600,
    }
    with TestClient(app) as c:
        r = c.post("/render", json={"url": URL, "limits": greedy}, headers=auth())
        out = r.json()
    ceiling = bl.RenderLimits(10, 100_000, 400_000, 20, 0.5, 5)
    assert out["limits"] == ceiling.as_dict()
    assert made[0].calls[0][2] == ceiling
    # Asking for less is honoured.
    with TestClient(app) as c:
        c.post(
            "/render",
            json={"url": URL, "limits": {"timeout_seconds": 3, "max_requests": 5}},
            headers=auth(),
        )
    calls = [call for r in made for call in r.calls]
    assert calls[1][2] == bl.RenderLimits(3, 100_000, 400_000, 5, 0.5, 5)


def test_oversized_html_is_refused_on_the_server():
    def big(ceiling, guard):
        return FakeRenderer(ceiling, guard, html="x" * 5000)

    app = svc.create_app(
        settings(max_bytes=1000), renderer_factory=big, environ={}, pacer=NoPace()
    )
    with TestClient(app) as c:
        out = c.post(
            "/render", json={"url": URL, "limits": {"max_bytes": 10**9}}, headers=auth()
        ).json()
    assert out["ok"] is False and out["kind"] == "render"
    assert "exceeds 1000 bytes" in out["error"] and "html" not in out


# Names that resolve to internal addresses (e.g. "db") pass this syntactic check
# and are refused at connect time by the guarded transport in the browser
# process (tests/test_collector_browser.py, names resolving internal).
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
    ],
)
def test_service_guards_urls_itself(url):
    app, made = service()
    with TestClient(app) as c:
        out = c.post("/render", json={"url": url}, headers=auth()).json()
    assert out["ok"] is False and out["kind"] == "unsafe_url"
    assert made == []  # never reached a browser


def test_render_errors_are_reported_by_kind():
    for error, kind in (
        (RobotsDisallowed("robots.txt disallows https://app.example/x"), "robots"),
        (CollectorError("https://app.example did not load in 45 s"), "render"),
    ):
        app, _ = service(renderer=FakeRenderer(None, None, error=error))
        with TestClient(app) as c:
            out = c.post("/render", json={"url": URL}, headers=auth()).json()
        assert out["ok"] is False and out["kind"] == kind
        assert out["error"] == str(error)
        assert out["request_log"] == [{"url": URL, "outcome": "fulfilled"}]


def test_pacing_per_host_across_callers_with_crawl_delay():
    now = [100.0]
    sleeps: list[float] = []

    def sleep(s):
        sleeps.append(s)

    pacer = svc.HostPacer(1.0, 30.0, clock=lambda: now[0], sleep=sleep)
    pacer.wait_turn("a.example")
    pacer.wait_turn("a.example")
    pacer.wait_turn("b.example")
    assert sleeps == [1.0]
    pacer.note_crawl_delays({"a.example": 10})
    pacer.wait_turn("a.example")  # its turn was reserved before the delay grew
    pacer.wait_turn("a.example")
    assert sleeps == [1.0, 2.0, 12.0]
    pacer.note_crawl_delays({"a.example": 100})
    pacer.wait_turn("a.example")  # turn at +22 s
    with pytest.raises(svc.RateLimited):
        pacer.wait_turn("a.example")  # would wait 122 s > 30


def test_rate_limited_render_is_refused_not_held():
    pacer = svc.HostPacer(1.0, 0.0, sleep=lambda s: None)
    app, made = service(pacer=pacer)
    with TestClient(app) as c:
        assert c.post("/render", json={"url": URL}, headers=auth()).json()["ok"]
        out = c.post("/render", json={"url": URL}, headers=auth()).json()
    assert out["kind"] == "rate_limited"
    assert len(made[0].calls) == 1


def test_busy_when_every_browser_is_taken():
    hold = threading.Event()
    r = FakeRenderer(None, None)
    r.hold = hold
    app, _ = service(renderer=r, max_concurrent=1, queue_wait_seconds=0.2)
    with TestClient(app) as c:
        first = threading.Thread(
            target=lambda: c.post("/render", json={"url": URL}, headers=auth())
        )
        first.start()
        deadline = time.monotonic() + 5
        while not r.calls and time.monotonic() < deadline:
            time.sleep(0.01)
        resp = c.post("/render", json={"url": "https://other.example/"}, headers=auth())
        hold.set()
        first.join(5)
    assert resp.status_code == 503


def test_renderers_closed_on_shutdown():
    app, made = service()
    with TestClient(app) as c:
        c.post("/render", json={"url": URL}, headers=auth())
    assert made and made[0].closed


# --- RemoteRenderer against the service in-process -----------------------------------------


def remote(app, token=TOKEN, limits=None) -> tuple[RemoteRenderer, TestClient]:
    c = TestClient(app)
    return RemoteRenderer("http://testserver", token, limits, http=c), c


def test_remote_renderer_round_trip():
    app, made = service()
    rr, c = remote(app, limits=bl.RenderLimits(timeout_seconds=7))
    with c:
        page = rr.render(URL, wait_for="li.notice")
    assert page.url == URL and page.html == "<ul><li>ok</li></ul>"
    assert page.requests == 3 and page.request_log == (
        {"url": URL, "outcome": "fulfilled"},
    )
    url, wait_for, limits = made[0].calls[0]
    assert (url, wait_for, limits.timeout_seconds) == (URL, "li.notice", 7)


def test_remote_renderer_maps_errors():
    rr, c = remote(service()[0], token=secrets.token_hex(32))
    with c, pytest.raises(CollectorError, match="BK_RENDERER_TOKEN"):
        rr.render(URL)
    app, _ = service(
        renderer=FakeRenderer(
            None, None, error=RobotsDisallowed("robots.txt disallows x")
        )
    )
    rr, c = remote(app)
    with c, pytest.raises(RobotsDisallowed):
        rr.render(URL)
    app, _ = service(renderer=FakeRenderer(None, None, error=CollectorError("boom")))
    rr, c = remote(app)
    with c, pytest.raises(CollectorError, match="boom"):
        rr.render(URL)
    # The client refuses internal URLs before sending; the service would too.
    rr, c = remote(service()[0])
    with c, pytest.raises(UnsafeURL):
        rr.render("http://10.0.0.1/")
    rr.check = lambda u: None
    with c, pytest.raises(UnsafeURL, match="blocked"):
        rr.render("http://10.0.0.1/")


def test_remote_renderer_unreachable_is_a_collector_error():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    rr = RemoteRenderer(f"http://127.0.0.1:{port}", TOKEN)
    with pytest.raises(CollectorError, match="cannot reach the renderer"):
        rr.render(URL)
    rr.close()


def test_browser_list_through_remote_renderer():
    """The collector, as the worker runs it, with a RemoteRenderer to the
    service: the page comes back rendered and parsed."""
    pages = {
        "https://app.example/tenders": '<ul><li class="notice"><a href="/n/1">'
        "Cold chain services</a></li></ul>",
        "https://app.example/tenders?page=2": "<ul></ul>",
        "https://app.example/n/1": "<p>detail</p>",
    }

    class Pages(FakeRenderer):
        def render(self, url, *, wait_for=None, limits=None):
            super().render(url, wait_for=wait_for, limits=limits)
            return bl.RenderedPage(url=url, html=pages[url])

    app, made = service(renderer=Pages(None, None))
    rr, c = remote(app)
    with c:
        col = build_collector(
            "browser_list", make_client(FakeWeb()), renderer_factory=lambda _: rr
        )
        items = col.fetch(source())
    assert [i.title for i in items] == ["Cold chain services"]
    assert made[0].calls[0][0] == "https://app.example/tenders"


# --- which renderer the API and worker use ---------------------------------------------


def test_default_renderer_is_remote_when_configured():
    s = Settings(
        _env_file=None,
        env="prod",
        renderer_url="http://renderer:8100/",
        renderer_token=TOKEN,
    )
    r = bl.default_renderer(make_client(FakeWeb()), s)
    assert isinstance(r, RemoteRenderer) and r.base_url == "http://renderer:8100"
    r.close()


def test_default_renderer_local_only_in_dev():
    dev = Settings(_env_file=None, env="dev")
    r = bl.default_renderer(make_client(FakeWeb()), dev)
    assert isinstance(r, bl.PlaywrightRenderer) and r._proc is None
    prod = Settings(_env_file=None, env="prod")
    with pytest.raises(CollectorError, match="BK_RENDERER_URL"):
        bl.default_renderer(make_client(FakeWeb()), prod)


def test_browser_list_refuses_to_run_without_a_renderer_in_prod(monkeypatch):
    from blackkite import config

    monkeypatch.setattr(
        config, "get_settings", lambda: Settings(_env_file=None, env="prod")
    )
    web = FakeWeb()
    col = build_collector("browser_list", make_client(web))
    with pytest.raises(CollectorError, match="needs the renderer service"):
        col.fetch(source())
    assert web.paths() == []  # nothing fetched, not even robots.txt


def test_settings_need_a_token_with_the_url():
    with pytest.raises(ValidationError, match="BK_RENDERER_TOKEN is not"):
        Settings(_env_file=None, renderer_url="http://renderer:8100")
    with pytest.raises(ValidationError, match="BK_RENDERER_TOKEN"):
        Settings(
            _env_file=None,
            renderer_url="http://renderer:8100",
            renderer_token="change-me",
        )
    with pytest.raises(ValidationError, match="BK_RENDERER_URL"):
        Settings(_env_file=None, renderer_url="ftp://renderer", renderer_token=TOKEN)
    with pytest.raises(ValidationError, match="BK_RENDERER_URL"):
        Settings(
            _env_file=None,
            renderer_url="http://u:p@renderer:8100",
            renderer_token=TOKEN,
        )
    s = Settings(_env_file=None, renderer_url=" ", renderer_token="")
    assert s.renderer_url is None and s.renderer_token is None


# --- real Chromium behind a real service on 127.0.0.1 --------------------------------------


@pytest.fixture
def renderer_service(local_server):  # noqa: F811 - fixture
    """The service under uvicorn on 127.0.0.1, rendering with PlaywrightRenderer
    behind the test-only guard that allows only the local page server."""
    page_port, hits = local_server
    started: list[bl.PlaywrightRenderer] = []

    def factory(ceiling, guard):
        r = bl.PlaywrightRenderer("BlackkiteBot/0.1 (+test)", ceiling, guard=guard)
        started.append(r)
        return r

    app = svc.create_app(
        settings(timeout_seconds=3, max_concurrent=1),
        guard=LoopbackOnlyGuard(page_port),
        renderer_factory=factory,
        environ={},
        pacer=NoPace(),
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="on"))
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started
    try:
        yield f"http://127.0.0.1:{port}", page_port, hits, app
    finally:
        server.should_exit = True
        thread.join(15)
        sock.close()
    # Shutting the service down closed its browsers: no process left behind.
    assert started
    for r in started:
        assert bl.tagged_pids(r.tag) == []


@real_browser
def test_real_service_renders_and_enforces_its_timeout(renderer_service):
    base, page_port, _hits, _app = renderer_service
    pages = f"http://127.0.0.1:{page_port}"
    rr = RemoteRenderer(
        base,
        TOKEN,
        bl.RenderLimits(timeout_seconds=600),  # asks for far more than allowed
        check=lambda u: None,  # the test pages are on loopback
    )
    try:
        page = rr.render(f"{pages}/list", wait_for="li.notice")
        assert "Rendered notice one" in page.html
        assert "http://10.0.0.1/secret" in page.blocked
        assert any(e["outcome"] == "blocked" for e in page.request_log)
        started = time.monotonic()
        with pytest.raises(CollectorError):
            rr.render(f"{pages}/spin")  # never finishes: killed at 3 s, not 600
        assert time.monotonic() - started < 30
        # The guard is the service's, not the caller's.
        with pytest.raises(UnsafeURL):
            rr.render("http://127.0.0.1:1/other-port")
    finally:
        rr.close()
