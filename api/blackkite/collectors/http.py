"""HTTP client for collectors (spec 10: identify honestly, rate-limit, cache, retry gently).

- Honest User-Agent: ``BlackkiteBot/0.1 (+BK_BOT_CONTACT_URL)``.
- Every request goes through ``GuardedTransport`` (sources/urlsafety.py): public
  addresses only, checked at connect time. Redirects are followed here, hop by hop,
  so each hop is re-validated and checked against robots.txt.
- robots.txt fetched once per origin and cached (24 h). 200: obeyed. 4xx other
  than 429: no rules (RFC 9309, "unavailable"). 429, 5xx or unreachable:
  everything disallowed (RFC 9309, "unreachable"; a 429 is the site asking us to
  back off), retried after the cache period. Crawl-delay raises the per-host delay.
- Per-host minimum delay between requests: the source's rate_limit, else the
  default; never under MIN_DELAY_SECONDS (1 s), whatever the caller passes.
- Conditional GET: ETag / Last-Modified stored in an ``HttpCache``; 304 returns the
  cached body.
- At most one retry, only on a connect error or a 5xx, after a backoff. Never on 4xx.
- Response size capped (Content-Length, raw bytes while streaming, and the decoded
  body: gzip/deflate are decompressed here in bounded steps); timeouts on every
  request.

Clock, sleep, resolver, transport and cache are injectable so tests run offline.
"""

from __future__ import annotations

import json
import time
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit

import httpx
from protego import Protego
from sqlalchemy.orm import Session, sessionmaker

from blackkite.collectors.base import CollectorError
from blackkite.config import Settings, user_agent
from blackkite.sources.urlsafety import (
    GuardedTransport,
    Resolver,
    check_url,
    system_resolver,
)

ROBOTS_TOKEN = "BlackkiteBot"
ROBOTS_TTL_SECONDS = 24 * 3600
ROBOTS_MAX_BYTES = 500_000
REDIRECT_CODES = (301, 302, 303, 307, 308)
# Floor for the per-host delay (also the lowest rate_limit a source may set).
MIN_DELAY_SECONDS = 1.0


class FetchError(CollectorError):
    """A fetch failed: HTTP error status, network error, too large, too many redirects."""


class RobotsDisallowed(FetchError):
    pass


class ResponseTooLarge(FetchError):
    pass


@dataclass(frozen=True)
class FetchResponse:
    url: str  # final URL, after redirects
    status: int
    headers: dict[str, str]
    content: bytes
    from_cache: bool = False

    @property
    def text(self) -> str:
        ctype = self.headers.get("content-type", "")
        charset = "utf-8"
        for part in ctype.split(";")[1:]:
            k, _, v = part.strip().partition("=")
            if k.lower() == "charset" and v:
                charset = v.strip("\"'")
        try:
            return self.content.decode(charset, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        try:
            return json.loads(self.content)
        except ValueError as e:
            raise FetchError(f"invalid JSON from {self.url}: {e}") from None


# --- bounded decoding -------------------------------------------------------------

ACCEPT_ENCODING = "gzip, deflate"


class _BoundedBody:
    """Collects a response body, decompressing gzip/deflate in steps of at most
    ``max_bytes + 1`` output bytes, and raises ResponseTooLarge as soon as either
    the raw or the decoded size passes ``max_bytes``."""

    def __init__(self, url: str, max_bytes: int, encoding: str | None) -> None:
        self.url = url
        self.max_bytes = max_bytes
        self.raw_size = 0
        self.size = 0
        self.chunks: list[bytes] = []
        self.encoding = (encoding or "").strip().lower()
        if self.encoding in ("", "identity"):
            self.decoder = None
        elif self.encoding in ("gzip", "x-gzip"):
            self.decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif self.encoding == "deflate":
            self.decoder = zlib.decompressobj()
        else:
            raise FetchError(f"unsupported content-encoding {encoding!r} from {url}")

    def _add(self, data: bytes) -> None:
        self.size += len(data)
        if self.size > self.max_bytes:
            raise ResponseTooLarge(f"{self.url} exceeds {self.max_bytes} bytes")
        self.chunks.append(data)

    def _decompress(self, data: bytes, first: bool) -> None:
        assert self.decoder is not None
        while data:
            try:
                out = self.decoder.decompress(data, self.max_bytes - self.size + 1)
            except zlib.error as e:
                if first and self.encoding == "deflate" and self.size == 0:
                    # Some servers send raw deflate without the zlib header.
                    self.decoder = zlib.decompressobj(-zlib.MAX_WBITS)
                    first = False
                    continue
                raise FetchError(f"bad compressed body from {self.url}: {e}") from None
            self._add(out)
            data = self.decoder.unconsumed_tail

    def feed(self, chunk: bytes) -> None:
        first = self.raw_size == 0
        self.raw_size += len(chunk)
        if self.raw_size > self.max_bytes:
            raise ResponseTooLarge(f"{self.url} exceeds {self.max_bytes} bytes")
        if self.decoder is None:
            self._add(chunk)
        else:
            self._decompress(chunk, first)

    def finish(self) -> bytes:
        if self.decoder is not None:
            try:
                self._add(self.decoder.flush())
            except zlib.error as e:
                raise FetchError(f"bad compressed body from {self.url}: {e}") from None
        return b"".join(self.chunks)


# --- conditional GET cache ---------------------------------------------------------


@dataclass(frozen=True)
class CachedResponse:
    etag: str | None
    last_modified: str | None
    content_type: str | None
    content: bytes


class HttpCache(Protocol):
    def get(self, url: str) -> CachedResponse | None: ...
    def put(self, url: str, entry: CachedResponse) -> None: ...


class MemoryHttpCache:
    """Per-process cache. Used by test runs so they write nothing to the database."""

    def __init__(self) -> None:
        self.entries: dict[str, CachedResponse] = {}

    def get(self, url: str) -> CachedResponse | None:
        return self.entries.get(url)

    def put(self, url: str, entry: CachedResponse) -> None:
        self.entries[url] = entry


class DbHttpCache:
    """The ``http_cache`` table, through its own short sessions (independent of the
    runner's transaction)."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def get(self, url: str) -> CachedResponse | None:
        from blackkite.db.models import HttpCache as Row

        with self.sessions() as s:
            row = s.get(Row, url)
            if row is None:
                return None
            return CachedResponse(
                row.etag, row.last_modified, row.content_type, row.content
            )

    def put(self, url: str, entry: CachedResponse) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from blackkite.db.models import HttpCache as Row

        values = {
            "url": url,
            "etag": entry.etag,
            "last_modified": entry.last_modified,
            "content_type": entry.content_type,
            "content": entry.content,
            "fetched_at": datetime.now(UTC),
        }
        stmt = insert(Row).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Row.url],
            set_={k: stmt.excluded[k] for k in values if k != "url"},
        )
        with self.sessions() as s:
            s.execute(stmt)
            s.commit()


# --- robots.txt --------------------------------------------------------------------


@dataclass
class _Robots:
    parser: Protego | None  # None with allow_all set means no rules
    allow_all: bool
    fetched_at: float

    def allowed(self, url: str) -> bool:
        if self.parser is None:
            return self.allow_all
        return bool(self.parser.can_fetch(url, ROBOTS_TOKEN))

    def crawl_delay(self) -> float | None:
        if self.parser is None:
            return None
        d = self.parser.crawl_delay(ROBOTS_TOKEN)
        return float(d) if d is not None else None


# --- client ------------------------------------------------------------------------


@dataclass
class FetchClient:
    user_agent: str
    transport: httpx.BaseTransport | None = None  # inner I/O; tests pass MockTransport
    resolver: Resolver = system_resolver
    cache: HttpCache = field(default_factory=MemoryHttpCache)
    timeout: float = 20.0
    max_bytes: int = 5_000_000
    default_delay: float = 5.0
    retry_backoff: float = 2.0
    max_redirects: int = 5
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            transport=GuardedTransport(self.transport, self.resolver),
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": self.user_agent},
        )
        self._last_request: dict[str, float] = {}
        self._host_delay: dict[str, float] = {}
        self._robots: dict[str, _Robots] = {}
        self.requests_made = 0
        # Set by ClientFetcher.remembering(): sees every successful response.
        self.on_response: Callable[[str, FetchResponse], None] | None = None

    # public -----------------------------------------------------------------------

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        delay: float | None = None,
        robots: bool = True,
        use_cache: bool = True,
    ) -> FetchResponse:
        """GET ``url``. ``delay`` is the minimum seconds between requests to its host.
        ``robots=False`` only for documented APIs called with a key (not crawling)."""
        if params:
            url = str(httpx.URL(url, params=params))
        resp = self._get(url, headers, delay, robots, use_cache)
        if self.on_response is not None:
            self.on_response(url, resp)
        return resp

    def _get(
        self,
        url: str,
        headers: dict[str, str] | None,
        delay: float | None,
        robots: bool,
        use_cache: bool,
    ) -> FetchResponse:
        for _ in range(self.max_redirects + 1):
            check_url(url)
            if robots and not self._robots_allow(url, delay):
                raise RobotsDisallowed(f"robots.txt disallows {url}")
            cached = self.cache.get(url) if use_cache else None
            h = dict(headers or {})
            if cached is not None:
                if cached.etag:
                    h["If-None-Match"] = cached.etag
                if cached.last_modified:
                    h["If-Modified-Since"] = cached.last_modified
            status, resp_headers, content = self._send(url, h, delay)
            if status in REDIRECT_CODES and "location" in resp_headers:
                url = urljoin(url, resp_headers["location"])
                continue
            if status == 304 and cached is not None:
                ctype = cached.content_type or ""
                return FetchResponse(
                    url, 200, {"content-type": ctype}, cached.content, True
                )
            if status >= 400:
                raise FetchError(f"HTTP {status} from {url}")
            if use_cache and status == 200:
                etag = resp_headers.get("etag")
                lm = resp_headers.get("last-modified")
                if etag or lm:
                    self.cache.put(
                        url,
                        CachedResponse(
                            etag, lm, resp_headers.get("content-type"), content
                        ),
                    )
            return FetchResponse(url, status, resp_headers, content)
        raise FetchError(f"too many redirects from {url}")

    def close(self) -> None:
        self._client.close()

    # internals ----------------------------------------------------------------------

    @staticmethod
    def _host(url: str) -> str:
        return (urlsplit(url).hostname or "").lower()

    def _wait_turn(self, host: str, delay: float | None) -> None:
        d = max(
            delay if delay is not None else self.default_delay,
            self._host_delay.get(host, 0.0),
            MIN_DELAY_SECONDS,
        )
        last = self._last_request.get(host)
        if last is not None:
            remaining = last + d - self.clock()
            if remaining > 0:
                self.sleep(remaining)

    def _send(
        self, url: str, headers: dict[str, str], delay: float | None
    ) -> tuple[int, dict[str, str], bytes]:
        host = self._host(url)
        for attempt in (0, 1):
            self._wait_turn(host, delay)
            try:
                result = self._once(url, headers)
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                if attempt == 0:
                    self.sleep(self.retry_backoff)
                    continue
                raise FetchError(f"cannot connect to {host}: {e}") from None
            except httpx.HTTPError as e:
                raise FetchError(f"{type(e).__name__} fetching {url}: {e}") from None
            finally:
                self._last_request[host] = self.clock()
            if 500 <= result[0] < 600 and attempt == 0:
                self.sleep(self.retry_backoff)
                continue
            return result
        raise AssertionError("unreachable")  # pragma: no cover

    def _once(
        self, url: str, headers: dict[str, str]
    ) -> tuple[int, dict[str, str], bytes]:
        self.requests_made += 1
        deadline = self.clock() + self.timeout * 3
        headers = {"Accept-Encoding": ACCEPT_ENCODING, **headers}
        with self._client.stream("GET", url, headers=headers) as r:
            declared = r.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > self.max_bytes:
                raise ResponseTooLarge(
                    f"{url} is {declared} bytes; limit {self.max_bytes}"
                )
            if r.is_stream_consumed:
                # Body already loaded and decoded by httpx (in-memory test
                # transports only; real responses always stream).
                out = _BoundedBody(url, self.max_bytes, None)
                out.feed(r.content)
            else:
                # Raw bytes, decompressed here in bounded steps: the size limit
                # holds for the decoded body, so a small compressed bomb cannot
                # blow memory.
                out = _BoundedBody(
                    url, self.max_bytes, r.headers.get("content-encoding")
                )
                for chunk in r.iter_raw():
                    out.feed(chunk)
                    if self.clock() > deadline:
                        raise FetchError(f"{url} took too long")
            content = out.finish()
            resp_headers = {
                k.lower(): v
                for k, v in r.headers.items()
                if k.lower() not in ("content-encoding", "content-length")
            }
            return r.status_code, resp_headers, content

    def _robots_allow(self, url: str, delay: float | None) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        entry = self._robots.get(origin)
        if entry is None or self.clock() - entry.fetched_at > ROBOTS_TTL_SECONDS:
            entry = self._load_robots(origin, delay)
            self._robots[origin] = entry
            cd = entry.crawl_delay()
            if cd is not None:
                self._host_delay[self._host(url)] = cd
        return entry.allowed(url)

    def _load_robots(self, origin: str, delay: float | None) -> _Robots:
        now = self.clock()
        url = origin + "/robots.txt"
        try:
            for _ in range(self.max_redirects + 1):
                check_url(url)
                status, headers, content = self._send(url, {}, delay)
                if status in REDIRECT_CODES and "location" in headers:
                    url = urljoin(url, headers["location"])
                    continue
                break
            else:
                return _Robots(None, False, now)
        except ResponseTooLarge:
            return _Robots(None, False, now)
        except FetchError:
            # Unreachable: assume complete disallow (RFC 9309 2.3.1.4).
            return _Robots(None, False, now)
        if status == 200:
            text = content[:ROBOTS_MAX_BYTES].decode("utf-8", errors="replace")
            return _Robots(Protego.parse(text), True, now)
        if 400 <= status < 500 and status != 429:
            return _Robots(None, True, now)  # unavailable: no restrictions
        # 429 (too many requests), 5xx: unreachable, disallow all until the entry
        # expires.
        return _Robots(None, False, now)


class ClientFetcher:
    """Adapts a ``FetchClient`` to the pipeline's ``Fetcher`` protocol
    (``get(url) -> (content_type, bytes, final_url)``), so the enrich stage's detail
    pages and PDFs go through the same URL guard, robots.txt, per-host delay,
    User-Agent, size cap and cache as the source's listing pages.

    Per-run memo: inside ``with fetcher.remembering():`` every page the collector
    fetches through the client is kept in memory (by requested, final and
    canonical URL), and ``get`` answers from it instead of requesting the page
    again, e.g. an html_list detail page that enrich would otherwise fetch twice.
    One ClientFetcher lives for one run; the memo is bounded (MEMO_MAX_ENTRIES,
    MEMO_MAX_BYTES) and dropped with it.
    """

    MEMO_MAX_ENTRIES = 500
    MEMO_MAX_BYTES = 50_000_000

    def __init__(self, client: FetchClient, delay: float | None = None) -> None:
        self.client = client
        self.delay = delay
        self.memo: dict[str, FetchResponse] = {}
        self._memo_bytes = 0
        self.memo_hits = 0

    @staticmethod
    def _keys(url: str) -> set[str]:
        from blackkite.pipeline.normalise import canonical_url

        return {url, canonical_url(url)}

    def _remember(self, requested: str, resp: FetchResponse) -> None:
        if (
            len(self.memo) >= self.MEMO_MAX_ENTRIES
            or self._memo_bytes + len(resp.content) > self.MEMO_MAX_BYTES
        ):
            return
        self._memo_bytes += len(resp.content)
        for key in self._keys(requested) | self._keys(resp.url):
            self.memo[key] = resp

    @contextmanager
    def remembering(self) -> Iterator[ClientFetcher]:
        previous = self.client.on_response
        self.client.on_response = self._remember
        try:
            yield self
        finally:
            self.client.on_response = previous

    def get(self, url: str) -> tuple[str, bytes, str]:
        """(content type, body, final URL after redirects)."""
        resp = next((self.memo[k] for k in self._keys(url) if k in self.memo), None)
        if resp is not None:
            self.memo_hits += 1
        else:
            resp = self.client.get(url, delay=self.delay)
        return resp.headers.get("content-type", ""), resp.content, resp.url


def make_fetch_client(
    settings: Settings,
    *,
    cache: HttpCache | None = None,
    transport: httpx.BaseTransport | None = None,
    resolver: Resolver = system_resolver,
    **kw: Any,
) -> FetchClient:
    return FetchClient(
        user_agent=user_agent(settings),
        transport=transport,
        resolver=resolver,
        cache=cache if cache is not None else MemoryHttpCache(),
        timeout=settings.fetch_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
        default_delay=settings.default_rate_limit,
        **kw,
    )


__all__ = [
    "CachedResponse",
    "ClientFetcher",
    "DbHttpCache",
    "FetchClient",
    "FetchError",
    "FetchResponse",
    "HttpCache",
    "MemoryHttpCache",
    "ResponseTooLarge",
    "RobotsDisallowed",
    "make_fetch_client",
]
