"""``browser_list`` collector (spec 4.2): JavaScript listing pages, rendered with
headless Chromium (Playwright), then parsed exactly like ``html_list``.

Config: the ``html_list`` config plus ``wait_for``, an optional CSS selector the
page must contain before it is read (for lists filled in by JavaScript).

Rendering sits behind the ``Renderer`` interface (``render(url, wait_for=...) ->
RenderedPage``, ``close()``) so tests use a fake. ``PlaywrightRenderer`` is the
real one. Its rules (spec 10: admin-entered config is untrusted):

- Top-level pages (list pages, detail pages): robots.txt checked and the
  source's per-host delay applied by the run's ``FetchClient`` before the browser
  is asked to load them (``robots_allowed`` / ``pace``).
- Every request the page makes is intercepted (``context.route("**/*")``) and,
  when allowed, performed by us through ``RequestGuard.transport()``: the same
  ``GuardedTransport`` as every other fetch, which resolves the host, refuses any
  non-public address and connects to the address it checked (no DNS-rebinding
  window). Chromium itself never opens a connection: it is launched with every
  host name mapped to nothing and a proxy that does not exist, so a request the
  route misses fails closed. Redirects are handed back to Chromium, which
  requests the next hop through the route again.
- Images, media, fonts and stylesheets are not fetched (not needed to read the
  DOM). Only GET, HEAD and POST are passed on. WebSockets are refused,
  service workers blocked.
- Per-host pacing inside a render (``subresource_delay``), at most
  ``max_requests`` requests per page, each response capped at ``max_bytes``
  (decoded, in bounded steps) and the whole render at ``total_bytes``; the final
  HTML is capped at ``max_bytes`` too.
- Hard timeout: the browser runs in a child process (its own process group); if
  a render is not back in ``timeout_seconds`` (+ start-up grace) the whole group
  is killed and the run gets a ``CollectorError``. Playwright's own timeouts are
  set inside that budget as well.
- No downloads (``accept_downloads=False``; attachment responses are refused),
  JavaScript dialogs dismissed, popups closed, a fresh non-persistent browser
  context per page (no profile on disk is reused).

The browser binary must already be installed (``PLAYWRIGHT_BROWSERS_PATH``);
nothing here downloads one. ``RequestGuard`` is picklable so the child process
gets the same guard; tests substitute a loopback-only guard of their own to
render a page served on 127.0.0.1. The production guard always blocks loopback.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import signal
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import Field, field_validator

from blackkite.collectors.base import CollectorError, RawItem
from blackkite.collectors.common import parse_model
from blackkite.collectors.html_list import HtmlListCollector, HtmlListConfig, _check_css
from blackkite.collectors.http import (
    ACCEPT_ENCODING,
    REDIRECT_CODES,
    FetchClient,
    FetchError,
    RobotsDisallowed,
    _BoundedBody,
)
from blackkite.sources.urlsafety import (
    GuardedTransport,
    UnsafeURL,
    check_url,
    system_resolver,
)

log = logging.getLogger("blackkite.collectors.browser_list")

BLOCKED_RESOURCE_TYPES = frozenset(
    {"image", "media", "font", "stylesheet", "texttrack", "manifest", "beacon", "ping"}
)
ALLOWED_METHODS = frozenset({"GET", "HEAD", "POST"})
# Headers Chromium sends that we must not forward as-is.
_DROP_REQUEST_HEADERS = frozenset(
    {"host", "content-length", "accept-encoding", "connection", "user-agent"}
)
_DROP_RESPONSE_HEADERS = frozenset(
    {"content-encoding", "content-length", "transfer-encoding", "connection"}
)
STARTUP_GRACE_SECONDS = 20.0
TAG_ENV = "BK_RENDERER_TAG"
MAX_REDIRECTS = 5
CHROMIUM_ARGS = [
    # The route interception (``_render_one``) is the primary control: every
    # request is fetched by us through the guard. These flags are the backstop
    # for anything the route misses.
    # Chromium resolves nothing itself. The rule also covers IP literals
    # (127.0.0.1, 2130706433, [::1], 10.0.0.1): they fail as NOTFOUND too
    # (checked against real Chromium in tests/test_collector_browser.py).
    "--host-resolver-rules=MAP * ~NOTFOUND",
    # Loopback goes to the dead proxy like everything else. Chromium bypasses
    # the proxy for loopback by default; Playwright adds this rule too, but not
    # when PLAYWRIGHT_DISABLE_FORCED_CHROMIUM_PROXIED_LOOPBACK is set, so we set
    # it ourselves (it comes after Playwright's own and wins).
    "--proxy-bypass-list=<-loopback>",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-sync",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-features=DnsOverHttps,NetworkPrediction",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--disable-dev-shm-usage",
]
# Requests the route misses fail here instead of reaching a network.
DEAD_PROXY = "http://127.0.0.1:9"


# --- config ------------------------------------------------------------------------------


class BrowserListConfig(HtmlListConfig):
    wait_for: str | None = Field(
        default=None,
        description="CSS selector to wait for before reading the page (for lists "
        "that JavaScript fills in).",
    )

    @field_validator("wait_for")
    @classmethod
    def _wait_for(cls, v: str | None) -> str | None:
        return v if v is None else _check_css(v)


def parse_config(config: dict[str, Any]) -> BrowserListConfig:
    return parse_model(BrowserListConfig, config, "browser_list")


# --- guard -------------------------------------------------------------------------------


class RequestGuard:
    """Production guard for browser requests: the URL guard and the guarded
    transport, public addresses only. Picklable (no state)."""

    def check(self, url: str) -> None:
        check_url(url)

    def transport(self) -> httpx.BaseTransport:
        return GuardedTransport(httpx.HTTPTransport(retries=0), system_resolver)


# --- renderer interface ----------------------------------------------------------------


@dataclass(frozen=True)
class RenderedPage:
    url: str  # final URL after redirects / script navigation
    html: str
    requests: int = 0
    blocked: tuple[str, ...] = ()  # URLs refused by the guard (first few)


class Renderer(Protocol):
    def render(self, url: str, *, wait_for: str | None = None) -> RenderedPage: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class RenderLimits:
    timeout_seconds: float = 45.0
    max_bytes: int = 5_000_000
    total_bytes: int = 20_000_000
    max_requests: int = 150
    subresource_delay: float = 0.25
    request_timeout: float = 20.0


# --- the child process ---------------------------------------------------------------------


@dataclass
class _Budget:
    deadline: float
    limits: RenderLimits
    requests: int = 0
    bytes: int = 0
    blocked: list[str] = field(default_factory=list)
    last_by_host: dict[str, float] = field(default_factory=dict)
    redirect_to: str | None = None  # main-frame redirect target

    def remaining(self) -> float:
        return self.deadline - time.monotonic()


class _Refused(Exception):
    """A request the route must abort (reason is the Playwright error code)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason


def _block(budget: _Budget, url: str) -> _Refused:
    if len(budget.blocked) < 20:
        budget.blocked.append(url[:300])
    return _Refused("blockedbyclient")


def _send_once(
    http: httpx.Client,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
    budget: _Budget,
) -> tuple[int, dict[str, str], bytes]:
    """One hop through the guard: check, pace, send, read under the caps."""
    if budget.remaining() <= 0 or budget.requests >= budget.limits.max_requests:
        raise _Refused("timedout")
    try:
        guard_check(url)
    except UnsafeURL:
        raise _block(budget, url) from None
    host = (urlsplit(url).hostname or "").lower()
    last = budget.last_by_host.get(host)
    if last is not None:
        wait = last + budget.limits.subresource_delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
    budget.requests += 1
    cap = max(0, min(budget.limits.max_bytes, budget.limits.total_bytes - budget.bytes))
    timeout = max(0.5, min(budget.limits.request_timeout, budget.remaining()))
    try:
        with http.stream(
            method, url, headers=headers, content=body, timeout=timeout
        ) as r:
            disposition = r.headers.get("content-disposition", "").lower()
            if disposition.startswith("attachment"):
                raise _Refused("blockedbyclient")  # no downloads
            if r.is_stream_consumed:
                # In-memory test transports only; real responses always stream.
                out = _BoundedBody(url, cap, None)
                out.feed(r.content)
            else:
                out = _BoundedBody(url, cap, r.headers.get("content-encoding"))
                for chunk in r.iter_raw():
                    out.feed(chunk)
                    if budget.remaining() <= 0:
                        raise FetchError(f"{url} took too long")
            content = out.finish()
            resp_headers: dict[str, str] = {}
            for k, v in r.headers.multi_items():
                k = k.lower()
                if k in _DROP_RESPONSE_HEADERS:
                    continue
                resp_headers[k] = f"{resp_headers[k]}\n{v}" if k in resp_headers else v
            status = r.status_code
    except UnsafeURL:
        raise _block(budget, url) from None
    except (httpx.HTTPError, CollectorError, OSError):
        raise _Refused("failed") from None
    finally:
        budget.last_by_host[host] = time.monotonic()
    budget.bytes += len(content)
    return status, resp_headers, content


def _is_main_navigation(req) -> bool:
    try:
        return bool(req.is_navigation_request()) and req.frame.parent_frame is None
    except Exception:  # noqa: BLE001 - fake requests in tests, detached frames
        return False


def _fetch_for_browser(
    http: httpx.Client, route, budget: _Budget, user_agent: str
) -> None:
    """Perform one intercepted request through the guarded client and hand the
    response to Chromium (or abort the request).

    Chromium does not send the hop after a fulfilled redirect back through the
    route (in testing it went to the dead proxy instead), so redirects never
    reach it: a subresource's redirects are followed here, hop by hop, each hop
    guarded; for a main-frame navigation the target is recorded and the request
    aborted, and ``_render_one`` navigates to the target (through the route)."""
    req = route.request
    if req.resource_type in BLOCKED_RESOURCE_TYPES or req.method not in ALLOWED_METHODS:
        route.abort("blockedbyclient")
        return
    headers = {
        k: v
        for k, v in req.all_headers().items()
        if k.lower() not in _DROP_REQUEST_HEADERS
    }
    headers["User-Agent"] = user_agent
    headers["Accept-Encoding"] = ACCEPT_ENCODING
    method = req.method
    body = req.post_data_buffer if method == "POST" else None
    url = req.url
    try:
        for _ in range(MAX_REDIRECTS + 1):
            status, resp_headers, content = _send_once(
                http, method, url, headers, body, budget
            )
            location = resp_headers.get("location")
            if status not in REDIRECT_CODES or not location:
                route.fulfill(status=status, headers=resp_headers, body=content)
                return
            target = urljoin(url, location.split("\n")[0].strip())
            if _is_main_navigation(req):
                budget.redirect_to = target
                route.abort("aborted")
                return
            if status in (301, 302, 303) and method == "POST":
                method, body = "GET", None
                headers.pop("content-type", None)
            url = target
        route.abort("failed")  # too many redirects
    except _Refused as r:
        route.abort(r.reason)


# The child process's guard (set once at start; module global so the route
# handler can reach it without capturing per-render state).
_GUARD: RequestGuard | None = None


def guard_check(url: str) -> None:
    assert _GUARD is not None
    _GUARD.check(url)


def _render_one(browser, http, job: dict[str, Any], limits: RenderLimits, ua: str):
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    budget = _Budget(deadline=time.monotonic() + limits.timeout_seconds, limits=limits)
    context = browser.new_context(
        user_agent=ua,
        accept_downloads=False,
        service_workers="block",
        java_script_enabled=True,
        ignore_https_errors=False,
    )
    try:
        context.route("**/*", lambda route: _fetch_for_browser(http, route, budget, ua))
        context.route_web_socket("**/*", lambda ws: ws.close())
        page = context.new_page()
        context.on("page", lambda p: p.close() if p != page else None)
        page.on("dialog", lambda d: d.dismiss())
        page.on("download", lambda d: d.cancel())

        def ms() -> float:
            return max(1.0, budget.remaining() * 1000)

        target = job["url"]
        for _ in range(MAX_REDIRECTS + 1):
            budget.redirect_to = None
            try:
                response = page.goto(
                    target, wait_until="domcontentloaded", timeout=ms()
                )
                break
            except PlaywrightTimeout:
                return {
                    "error": f"{target} did not load in {limits.timeout_seconds:g} s"
                }
            except PlaywrightError as e:
                if budget.redirect_to:
                    target = budget.redirect_to  # guarded again on the next goto
                    continue
                if budget.blocked and "ERR_BLOCKED_BY_CLIENT" in str(e):
                    return {
                        "error": f"blocked: {budget.blocked[0]} is not a public address"
                    }
                return {"error": f"cannot load {target}: {str(e).splitlines()[0]}"}
        else:
            return {"error": f"too many redirects from {job['url']}"}
        if response is not None and response.status >= 400:
            return {"error": f"HTTP {response.status} from {job['url']}"}
        if job.get("wait_for"):
            try:
                page.wait_for_selector(job["wait_for"], state="attached", timeout=ms())
            except PlaywrightTimeout:
                return {
                    "error": f"{job['wait_for']!r} did not appear on {job['url']} "
                    f"within {limits.timeout_seconds:g} s"
                }
        try:
            page.wait_for_load_state("networkidle", timeout=min(3000.0, ms()))
        except PlaywrightTimeout:
            pass  # pages that poll forever: read what is there
        html = page.content()
        if len(html.encode("utf-8", errors="replace")) > limits.max_bytes:
            return {"error": f"rendered {job['url']} exceeds {limits.max_bytes} bytes"}
        return {
            "url": page.url,
            "html": html,
            "requests": budget.requests,
            "blocked": list(budget.blocked),
        }
    finally:
        context.close()


def _child_main(
    conn, user_agent: str, limits: RenderLimits, guard: RequestGuard, tag: str
):
    """Child process: one headless browser, renders jobs sent over ``conn``."""
    global _GUARD
    os.setsid()  # own process group, so the parent can kill the browser with us
    # Inherited by the Playwright driver and Chromium (which Playwright starts in
    # process groups of their own), so the parent can find and kill all of them.
    os.environ[TAG_ENV] = tag
    _GUARD = guard
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=CHROMIUM_ARGS,
                proxy={"server": DEAD_PROXY},
                downloads_path=None,
            )
            http = httpx.Client(
                transport=guard.transport(), follow_redirects=False, trust_env=False
            )
            conn.send({"ready": True})
            while True:
                job = conn.recv()
                if job is None:
                    break
                try:
                    result = _render_one(browser, http, job, limits, user_agent)
                except Exception as e:  # noqa: BLE001 - reported; browser kept for the next job
                    result = {"error": f"render failed: {type(e).__name__}: {e}"[:500]}
                conn.send(result)
            http.close()
            browser.close()
    except Exception as e:  # noqa: BLE001 - reported to the parent, which raises
        try:
            conn.send({"error": f"browser failed: {type(e).__name__}: {e}"[:500]})
        except OSError:
            pass


def tagged_pids(tag: str) -> list[int]:
    """PIDs of live processes whose environment holds ``TAG_ENV=tag`` (Linux
    /proc; empty elsewhere)."""
    needle = f"{TAG_ENV}={tag}".encode()
    out = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return out
    for name in entries:
        if not name.isdigit() or int(name) == os.getpid():
            continue
        try:
            with open(f"/proc/{name}/environ", "rb") as f:
                env = f.read()
        except OSError:
            continue
        if needle in env.split(b"\0"):
            out.append(int(name))
    return out


class PlaywrightRenderer:
    """``Renderer`` using headless Chromium in a child process (see module doc)."""

    def __init__(
        self,
        user_agent: str,
        limits: RenderLimits | None = None,
        guard: RequestGuard | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.limits = limits or RenderLimits()
        self.guard = guard or RequestGuard()
        self._proc = None
        self._conn = None
        self.tag = uuid.uuid4().hex

    def _start(self) -> None:
        ctx = multiprocessing.get_context("spawn")
        parent, child = ctx.Pipe()
        proc = ctx.Process(
            target=_child_main,
            args=(child, self.user_agent, self.limits, self.guard, self.tag),
            daemon=True,
        )
        proc.start()
        child.close()
        self._proc, self._conn = proc, parent
        if not parent.poll(STARTUP_GRACE_SECONDS + self.limits.timeout_seconds):
            self._kill()
            raise CollectorError("headless browser did not start in time")
        msg = parent.recv()
        if not msg.get("ready"):
            self._kill()
            raise CollectorError(msg.get("error") or "headless browser failed to start")

    def _kill(self) -> None:
        proc, conn = self._proc, self._conn
        self._proc = self._conn = None
        if conn is not None:
            conn.close()
        if proc is None:
            return
        if proc.pid is not None and proc.is_alive():
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
        proc.join(5)
        # The driver and browser run in process groups of their own: kill every
        # process carrying this renderer's tag (and only those).
        for pid in tagged_pids(self.tag):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def render(self, url: str, *, wait_for: str | None = None) -> RenderedPage:
        self.guard.check(url)  # the child checks every request again
        return self._render_in_child(url, wait_for)

    def _render_in_child(self, url: str, wait_for: str | None) -> RenderedPage:
        if self._proc is None:
            self._start()
        assert self._conn is not None
        try:
            self._conn.send({"url": url, "wait_for": wait_for})
            if not self._conn.poll(self.limits.timeout_seconds + 5):
                self._kill()
                raise CollectorError(
                    f"rendering {url} took longer than {self.limits.timeout_seconds:g} s"
                )
            result = self._conn.recv()
        except (EOFError, OSError, BrokenPipeError):
            self._kill()
            raise CollectorError(f"headless browser died rendering {url}") from None
        if "error" in result:
            raise CollectorError(result["error"])
        return RenderedPage(
            url=result["url"],
            html=result["html"],
            requests=result["requests"],
            blocked=tuple(result["blocked"]),
        )

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.send(None)
                if self._proc is not None:
                    self._proc.join(10)
            except (OSError, BrokenPipeError):
                pass
        self._kill()


RendererFactory = Callable[[FetchClient], Renderer]


def default_renderer(client: FetchClient) -> Renderer:
    return PlaywrightRenderer(
        client.user_agent,
        RenderLimits(
            max_bytes=client.max_bytes,
            total_bytes=4 * client.max_bytes,
            request_timeout=client.timeout,
        ),
    )


# --- the collector -------------------------------------------------------------------------


class BrowserListCollector(HtmlListCollector):
    def __init__(
        self,
        client: FetchClient,
        *,
        renderer_factory: RendererFactory = default_renderer,
        preview: bool = False,
        **kw,
    ) -> None:
        super().__init__(client, preview=preview, **kw)
        self.renderer_factory = renderer_factory
        self._renderer: Renderer | None = None

    def _config(self, config: dict[str, Any]) -> BrowserListConfig:
        return parse_config(config)

    def _page(self, url: str, delay: float | None, cfg, *, detail: bool):
        if not self.client.robots_allowed(url, delay):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        self.client.pace(url, delay)
        if self._renderer is None:
            self._renderer = self.renderer_factory(self.client)
        page = self._renderer.render(url, wait_for=None if detail else cfg.wait_for)
        if page.blocked:
            log.info("render of %s: blocked %d request(s)", url, len(page.blocked))
        return page.url, page.html

    def fetch(self, source) -> list[RawItem]:
        try:
            return super().fetch(source)
        finally:
            if self._renderer is not None:
                self._renderer.close()
                self._renderer = None
