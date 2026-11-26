"""``RemoteRenderer``: the ``Renderer`` the API and worker use for
``browser_list`` (decision 46). It sends each page to the renderer service at
``BK_RENDERER_URL`` with the shared ``BK_RENDERER_TOKEN`` and turns the answer
back into a ``RenderedPage`` or the same errors the local renderer raises
(``RobotsDisallowed``, ``UnsafeURL``, ``CollectorError``).

The renderer is on the compose internal network (a private address by design),
so this client does not go through the public-address guard; it never follows
redirects, ignores proxy variables, and caps the answer it reads.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from pydantic import SecretStr

from blackkite.collectors.base import CollectorError
from blackkite.collectors.browser_list import (
    STARTUP_GRACE_SECONDS,
    RenderedPage,
    RenderLimits,
)
from blackkite.collectors.http import RobotsDisallowed
from blackkite.sources.urlsafety import UnsafeURL, check_url

# On top of the render timeout: browser start-up, waiting for a free browser
# and for the host's turn on the service.
EXTRA_WAIT_SECONDS = STARTUP_GRACE_SECONDS + 60.0
# JSON overhead allowed on top of the page itself (escaping, request log).
ANSWER_OVERHEAD_BYTES = 2_000_000


class RemoteRenderer:
    def __init__(
        self,
        base_url: str,
        token: SecretStr | str,
        limits: RenderLimits | None = None,
        *,
        http: httpx.Client | None = None,
        check: Callable[[str], object] = check_url,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = (
            token.get_secret_value() if isinstance(token, SecretStr) else token
        )
        self.limits = limits or RenderLimits()
        self._own_http = http is None
        self.http = http or httpx.Client(follow_redirects=False, trust_env=False)
        self.check = check  # tests only replace it (a page on 127.0.0.1)
        self.last_request_log: tuple[dict[str, Any], ...] = ()

    def render(self, url: str, *, wait_for: str | None = None) -> RenderedPage:
        self.check(url)  # the service checks again, with DNS
        payload = {"url": url, "wait_for": wait_for, "limits": self.limits.as_dict()}
        timeout = self.limits.timeout_seconds + EXTRA_WAIT_SECONDS
        cap = 2 * self.limits.max_bytes + ANSWER_OVERHEAD_BYTES
        try:
            with self.http.stream(
                "POST",
                f"{self.base_url}/render",
                json=payload,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=httpx.Timeout(timeout, connect=10.0),
            ) as r:
                if r.status_code == 401:
                    raise CollectorError(
                        "the renderer refused our token: BK_RENDERER_TOKEN must be "
                        "the same for the renderer, api and worker"
                    )
                if r.status_code == 503:
                    raise CollectorError("the renderer is busy; try again later")
                if r.status_code != 200:
                    raise CollectorError(f"the renderer answered HTTP {r.status_code}")
                chunks, size = [], 0
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > cap:
                        raise CollectorError("the renderer's answer is too large")
                    chunks.append(chunk)
        except httpx.TimeoutException:
            raise CollectorError(
                f"the renderer did not answer for {url} in {timeout:g} s"
            ) from None
        except httpx.HTTPError as e:
            raise CollectorError(
                f"cannot reach the renderer at {self.base_url}: {type(e).__name__}"
            ) from None
        try:
            data = httpx.Response(200, content=b"".join(chunks)).json()
        except ValueError:
            raise CollectorError(
                "the renderer sent an answer that is not JSON"
            ) from None
        if not isinstance(data, dict):
            raise CollectorError("the renderer sent an unexpected answer")
        self.last_request_log = tuple(data.get("request_log") or ())
        if not data.get("ok"):
            error = str(data.get("error") or "render failed")
            kind = data.get("kind")
            if kind == "robots":
                raise RobotsDisallowed(error)
            if kind == "unsafe_url":
                raise UnsafeURL(error)
            raise CollectorError(error)
        try:
            return RenderedPage(
                url=str(data["url"]),
                html=str(data["html"]),
                requests=int(data.get("requests") or 0),
                blocked=tuple(str(b) for b in data.get("blocked") or ()),
                request_log=self.last_request_log,
            )
        except (KeyError, TypeError, ValueError):
            raise CollectorError("the renderer sent an incomplete answer") from None

    def close(self) -> None:
        if self._own_http:
            self.http.close()
