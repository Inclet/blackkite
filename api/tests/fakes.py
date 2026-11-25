"""Offline fakes for collector tests: a fake web (MockTransport), resolver and clock.

All content served here is synthetic and written for these tests.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from blackkite.collectors.http import FetchClient, MemoryHttpCache

PUBLIC_IP = "93.184.215.14"

Handler = Callable[[httpx.Request], httpx.Response]


def public_resolver(host: str, port: int) -> list[str]:
    return [PUBLIC_IP]


@dataclass
class FakeClock:
    now: float = 1000.0
    sleeps: list[float] = field(default_factory=list)

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@dataclass
class FakeWeb:
    """Routes by (Host header, path?query). Records every request it receives.

    robots.txt is a 404 (no rules) unless a route for it is added.
    """

    routes: dict[tuple[str, str], Handler | httpx.Response] = field(
        default_factory=dict
    )
    requests: list[httpx.Request] = field(default_factory=list)

    def add(self, host: str, target: str, response: Handler | httpx.Response) -> None:
        self.routes[(host, target)] = response

    def html(self, host: str, target: str, body: str, **headers: str) -> None:
        self.add(
            host,
            target,
            httpx.Response(
                200,
                text=body,
                headers={"content-type": "text/html; charset=utf-8", **headers},
            ),
        )

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host = request.headers["host"]
        target = request.url.raw_path.decode()
        route = self.routes.get((host, target))
        if route is None and "?" in target:
            route = self.routes.get((host, target.split("?", 1)[0]))
        if route is None:
            return httpx.Response(404, text="not found")
        return route(request) if callable(route) else route

    def paths(self, host: str | None = None) -> list[str]:
        return [
            r.url.raw_path.decode()
            for r in self.requests
            if host is None or r.headers["host"] == host
        ]

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)


def make_client(web: FakeWeb, clock: FakeClock | None = None, **kw) -> FetchClient:
    clock = clock or FakeClock()
    return FetchClient(
        user_agent="BlackkiteBot/0.1 (+https://example.com/bot)",
        transport=web.transport,
        resolver=kw.pop("resolver", public_resolver),
        cache=kw.pop("cache", MemoryHttpCache()),
        sleep=clock.sleep,
        clock=clock,
        default_delay=kw.pop("default_delay", 1.0),
        **kw,
    )
