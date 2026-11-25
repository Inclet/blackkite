"""``search_query`` collector (spec 4.2) on the Brave Search web API (decision 11).

Config (validated by ``SearchQueryConfig``)::

    {
      "queries": ["tender transport Kigali", "invitation for bids logistics"],
      "domains": ["jobinrwanda.com"],     # optional; adds site: and filters results
      "recency_days": 7,                  # optional; Brave freshness pd/pw/pm/py
      "count": 20                         # results per query, 1-20
    }

The key comes from BRAVE_API_KEY. Without it the collector raises
``CollectorError("no search key configured")`` before any request is made.
Requests are spaced at least ``BRAVE_MIN_INTERVAL`` seconds apart (Brave's free
plan allows 1 request per second; we stay under it).

Response fields used (Brave web search JSON, from memory of the public docs;
NOT verified against the live API in this phase): ``web.results[]`` with
``title``, ``url``, ``description``, ``page_age``, ``age``, ``meta_url.hostname``,
``profile.name``, ``extra_snippets``. ``title``/``description`` may contain
<strong> highlight tags; they are stripped.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
)

from blackkite.collectors.base import CollectorError, RawItem
from blackkite.collectors.http import FetchClient
from blackkite.sources.urlsafety import UnsafeURL, check_url

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_MIN_INTERVAL = 1.1
_TAGS = re.compile(r"<[^>]{0,200}>")
_WS = re.compile(r"\s+")
_DOMAIN = re.compile(
    r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)


class SearchQueryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    queries: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=300)]],
        Field(min_length=1, max_length=20),
    ] = Field(description="Search queries, one request each per run.")
    domains: Annotated[list[str], Field(max_length=10)] = Field(
        default=[], description="Only keep results from these domains (site: filter)."
    )
    recency_days: Annotated[int, Field(ge=1, le=365)] | None = Field(
        default=None, description="Only results from roughly the last N days."
    )
    count: Annotated[int, Field(ge=1, le=20)] = Field(
        default=20, description="Results per query (1-20)."
    )

    @field_validator("domains")
    @classmethod
    def _domains(cls, v: list[str]) -> list[str]:
        out = []
        for d in v:
            d = d.strip().lower().rstrip(".")
            if not _DOMAIN.match(d):
                raise ValueError(f"not a domain name: {d!r}")
            try:
                check_url(f"https://{d}/")
            except UnsafeURL as e:
                raise ValueError(str(e)) from None
            out.append(d)
        return out

    def freshness(self) -> str | None:
        d = self.recency_days
        if d is None:
            return None
        return "pd" if d <= 1 else "pw" if d <= 7 else "pm" if d <= 31 else "py"

    def query_text(self, q: str) -> str:
        if not self.domains:
            return q
        sites = [f"site:{d}" for d in self.domains]
        return f"{q} {sites[0]}" if len(sites) == 1 else f"{q} ({' OR '.join(sites)})"

    def host_allowed(self, host: str) -> bool:
        host = host.lower()
        return not self.domains or any(
            host == d or host.endswith("." + d) for d in self.domains
        )


def parse_config(config: dict[str, Any]) -> SearchQueryConfig:
    if config.get("placeholder"):
        raise CollectorError(
            "source config is a placeholder; set it after the M0 access test"
        )
    try:
        return SearchQueryConfig.model_validate(config)
    except ValidationError as e:
        raise CollectorError(f"invalid search_query config: {e}") from None


def _text(v: Any, limit: int = 2000) -> str | None:
    if not isinstance(v, str):
        return None
    v = _WS.sub(" ", html.unescape(_TAGS.sub("", v))).strip()
    return v[:limit] or None


class SearchQueryCollector:
    def __init__(
        self,
        client: FetchClient,
        api_key: SecretStr | None,
        *,
        preview: bool = False,
        now=lambda: datetime.now(UTC),
    ) -> None:
        self.client = client
        self.api_key = api_key
        self.preview = preview
        self.now = now

    def fetch(self, source) -> list[RawItem]:
        cfg = parse_config(source.config or {})
        key = self.api_key.get_secret_value() if self.api_key else ""
        if not key:
            raise CollectorError("no search key configured")
        queries = cfg.queries[:1] if self.preview else cfg.queries
        items: list[RawItem] = []
        seen: set[str] = set()
        for q in queries:
            params: dict[str, Any] = {"q": cfg.query_text(q), "count": cfg.count}
            if (fresh := cfg.freshness()) is not None:
                params["freshness"] = fresh
            resp = self.client.get(
                BRAVE_URL,
                params=params,
                headers={"Accept": "application/json", "X-Subscription-Token": key},
                delay=BRAVE_MIN_INTERVAL,
                robots=False,  # documented API called with a key, not crawling
                use_cache=False,
            )
            data = resp.json()
            results = (
                (data.get("web") or {}).get("results")
                if isinstance(data, dict)
                else None
            )
            if not isinstance(results, list):
                continue
            fetched_at = self.now()
            for r in results:
                if not isinstance(r, dict):
                    continue
                url = r.get("url")
                title = _text(r.get("title"), 500)
                if not isinstance(url, str) or not title or url in seen:
                    continue
                try:
                    check_url(url)
                except UnsafeURL:
                    continue
                if not cfg.host_allowed(urlsplit(url).hostname or ""):
                    continue
                seen.add(url)
                extra = {"query": q}
                if isinstance(r.get("age"), str):
                    extra["age"] = r["age"]
                if isinstance((r.get("profile") or {}).get("name"), str):
                    extra["site_name"] = r["profile"]["name"]
                snippets = r.get("extra_snippets")
                if isinstance(snippets, list):
                    joined = " … ".join(
                        s for s in (_text(x, 500) for x in snippets) if s
                    )
                    if joined:
                        extra["extra_snippets"] = joined[:2000]
                items.append(
                    RawItem(
                        source_id=source.id,
                        url=url,
                        title=title,
                        fetched_at=fetched_at,
                        listed_published=_text(r.get("page_age"), 100)
                        or _text(r.get("age"), 100),
                        snippet=_text(r.get("description")),
                        extra=extra,
                    )
                )
        return items
