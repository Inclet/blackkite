"""The renderer HTTP service (decision 46), run as ``bk renderer``.

Headless Chromium for ``browser_list`` runs here, in its own container with no
secrets, instead of in the API or worker. Callers (the API's test runs and the
worker's scheduled runs, through ``RemoteRenderer``) authenticate with the
shared ``BK_RENDERER_TOKEN``.

Routes:

- ``GET /healthz``: ``{"ok": true}``, no token (container health check).
- ``POST /render`` (``Authorization: Bearer <token>``): ``{url, wait_for?,
  limits?}`` -> ``{ok, url, html, requests, blocked, request_log, limits}`` or
  ``{ok: false, kind, error, request_log, limits}``. ``kind`` is ``unsafe_url``,
  ``robots``, ``rate_limited`` or ``render``. 401 without the right token, 503
  when every browser stays busy for ``queue_wait_seconds``, 422 for a malformed
  body.

The caller is not trusted. Whatever it sends, the service itself:

- puts the URL through the production URL guard (public addresses only) and
  renders with ``PlaywrightRenderer``, whose route sends every request through
  the guarded transport, checks robots.txt on every main-frame navigation
  (decision 48), paces requests per host and caps sizes and request counts;
- clamps the requested limits to its own ceilings (``RenderLimits.within``);
- paces renders per host across all callers (``min_host_delay``, raised by any
  Crawl-delay the browser saw);
- kills a render that overruns its timeout (the child process group).

No API docs are served.
"""

from __future__ import annotations

import hmac
import logging
import os
import queue
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from typing import Any
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from blackkite.collectors.base import CollectorError
from blackkite.collectors.browser_list import (
    PlaywrightRenderer,
    RenderedPage,
    RenderLimits,
    RequestGuard,
)
from blackkite.collectors.html_list import _check_css
from blackkite.collectors.http import RobotsDisallowed
from blackkite.renderer.settings import (
    RendererConfigError,
    RendererSettings,
    check_environment,
)
from blackkite.sources.urlsafety import MAX_URL_LENGTH, UnsafeURL

log = logging.getLogger("blackkite.renderer")

__all__ = ["RendererConfigError", "create_app"]


# --- request / response --------------------------------------------------------------


class LimitsIn(BaseModel):
    """What a caller asks for; every field optional, clamped to the ceilings."""

    model_config = ConfigDict(extra="forbid")
    timeout_seconds: float | None = Field(default=None, gt=0)
    max_bytes: int | None = Field(default=None, ge=1)
    total_bytes: int | None = Field(default=None, ge=1)
    max_requests: int | None = Field(default=None, ge=0)
    subresource_delay: float | None = Field(default=None, ge=0)
    request_timeout: float | None = Field(default=None, gt=0)


class RenderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=MAX_URL_LENGTH)
    wait_for: str | None = None
    limits: LimitsIn | None = None

    @field_validator("wait_for")
    @classmethod
    def _wait_for(cls, v: str | None) -> str | None:
        return v if v is None else _check_css(v)


def effective_limits(asked: LimitsIn | None, ceiling: RenderLimits) -> RenderLimits:
    if asked is None:
        return ceiling
    given = {k: v for k, v in asked.model_dump().items() if v is not None}
    return RenderLimits.from_dict({**ceiling.as_dict(), **given}).within(ceiling)


# --- per-host pacing across callers ----------------------------------------------------


class RateLimited(Exception):
    pass


class HostPacer:
    """At least ``min_delay`` (or the host's Crawl-delay) between two renders of
    pages on one host. Turns are reserved under a lock, so concurrent callers
    queue rather than collide; a wait over ``max_wait`` is refused."""

    def __init__(
        self,
        min_delay: float,
        max_wait: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_delay = min_delay
        self.max_wait = max_wait
        self.clock = clock
        self.sleep = sleep
        self._lock = threading.Lock()
        self._next: dict[str, float] = {}  # host -> earliest next turn
        self._delay: dict[str, float] = {}  # host -> Crawl-delay seen

    def delay_for(self, host: str) -> float:
        return max(self.min_delay, self._delay.get(host, 0.0))

    def wait_turn(self, host: str) -> None:
        with self._lock:
            now = self.clock()
            turn = max(now, self._next.get(host, now))
            wait = turn - now
            if wait > self.max_wait:
                raise RateLimited(
                    f"{host}: next render allowed in {wait:.0f} s; try again later"
                )
            self._next[host] = turn + self.delay_for(host)
        if wait > 0:
            self.sleep(wait)

    def note_crawl_delays(self, delays: Mapping[str, float]) -> None:
        with self._lock:
            for host, d in delays.items():
                d = float(d)
                if d > self._delay.get(host, 0.0):
                    self._delay[host] = d


# --- browser pool --------------------------------------------------------------------


class Busy(Exception):
    pass


class RendererPool:
    """``size`` renderers, each started on first use and kept for later renders."""

    def __init__(self, factory: Callable[[], Any], size: int) -> None:
        self.factory = factory
        self._idle: queue.Queue[Any] = queue.Queue()
        self._all: list[Any] = []
        self._lock = threading.Lock()
        for _ in range(size):
            self._idle.put(None)

    @contextmanager
    def slot(self, timeout: float) -> Iterator[Any]:
        try:
            r = self._idle.get(timeout=timeout)
        except queue.Empty:
            raise Busy from None
        try:
            if r is None:
                r = self.factory()
                with self._lock:
                    self._all.append(r)
            yield r
        finally:
            self._idle.put(r)

    def close(self) -> None:
        with self._lock:
            renderers, self._all = list(self._all), []
        for r in renderers:
            try:
                r.close()
            except Exception:
                log.exception("closing a renderer failed")


# --- app -----------------------------------------------------------------------------


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value.strip() else None


def create_app(
    settings: RendererSettings | None = None,
    *,
    guard: RequestGuard | None = None,
    renderer_factory: Callable[[RenderLimits, RequestGuard], Any] | None = None,
    environ: Mapping[str, str] | None = None,
    pacer: HostPacer | None = None,
) -> FastAPI:
    """The service. Raises ``RendererConfigError`` if a forbidden secret is in
    the environment, and pydantic's ValidationError without a usable
    BK_RENDERER_TOKEN. ``guard`` and ``renderer_factory`` are for tests (a
    loopback-only guard, a fake renderer); production uses ``RequestGuard``
    and ``PlaywrightRenderer``."""
    check_environment(os.environ if environ is None else environ)
    settings = settings or RendererSettings()  # type: ignore[call-arg]
    guard = guard or RequestGuard()
    ceiling = settings.ceiling()
    ua = settings.user_agent()
    token = settings.token.get_secret_value().encode()

    def make() -> Any:
        if renderer_factory is not None:
            return renderer_factory(ceiling, guard)
        return PlaywrightRenderer(ua, ceiling, guard=guard)

    pool = RendererPool(make, settings.max_concurrent)
    pacer = pacer or HostPacer(settings.min_host_delay, settings.max_pace_wait_seconds)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            pool.close()

    app = FastAPI(
        title="Blackkite renderer",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.pool = pool
    app.state.pacer = pacer
    app.state.ceiling = ceiling

    def authorised(authorization: str | None = Header(default=None)) -> None:
        given = _bearer(authorization)
        if given is None or not hmac.compare_digest(given.encode(), token):
            raise HTTPException(
                401, "missing or wrong token", headers={"WWW-Authenticate": "Bearer"}
            )

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/render", dependencies=[Depends(authorised)])
    def render(body: RenderIn) -> dict[str, Any]:
        limits = effective_limits(body.limits, ceiling)
        out: dict[str, Any] = {"limits": limits.as_dict(), "request_log": []}

        def failed(kind: str, error: str) -> dict[str, Any]:
            log.info("render of %s refused (%s): %s", body.url[:200], kind, error)
            return {**out, "ok": False, "kind": kind, "error": error[:1000]}

        try:
            guard.check(body.url)
        except UnsafeURL as e:
            return failed("unsafe_url", f"blocked: {e}")
        host = (urlsplit(body.url).hostname or "").lower()
        try:
            pacer.wait_turn(host)
        except RateLimited as e:
            return failed("rate_limited", str(e))
        try:
            with pool.slot(settings.queue_wait_seconds) as renderer:
                try:
                    page: RenderedPage = renderer.render(
                        body.url, wait_for=body.wait_for, limits=limits
                    )
                finally:
                    pacer.note_crawl_delays(
                        getattr(renderer, "last_crawl_delays", None) or {}
                    )
                    out["request_log"] = list(
                        getattr(renderer, "last_request_log", None) or ()
                    )
        except Busy:
            raise HTTPException(503, "every browser is busy; try again") from None
        except RobotsDisallowed as e:
            return failed("robots", str(e))
        except UnsafeURL as e:
            return failed("unsafe_url", f"blocked: {e}")
        except CollectorError as e:
            return failed("render", str(e))
        # Server-side cap, whatever the renderer did.
        if len(page.html.encode("utf-8", errors="replace")) > limits.max_bytes:
            return failed(
                "render", f"rendered {body.url} exceeds {limits.max_bytes} bytes"
            )
        return {
            **out,
            "ok": True,
            "url": page.url,
            "html": page.html,
            "requests": page.requests,
            "blocked": list(page.blocked),
            "request_log": list(page.request_log or out["request_log"]),
        }

    return app
