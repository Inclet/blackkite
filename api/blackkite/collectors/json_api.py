"""``json_api`` collector (spec 4.2): sites whose front end calls a JSON API.

Config (``JsonApiConfig``)::

    {
      "endpoint": "https://portal.example/api/notices",
      "params": {"country": "RW", "size": 50},         # query string, optional
      "pagination": {"mode": "page", "param": "page", "start": 1, "max_pages": 3},
      #          or {"mode": "next_link", "path": "links.next", "max_pages": 3}
      "mapping": {
        "list": "data.items",          # dotted path to the array of items ("" = root)
        "title": "title",              # required
        "url": "links.self",           # required: the notice link (or an id, below)
        "url_template": "https://portal.example/notice/{value}",   # optional
        "date": "published",
        "deadline": "deadline",
        "organisation": "buyer.name",
        "snippet": "description",
        "extra": {"reference": "ref"}  # optional, kept in RawItem.extra
      },
      "max_bytes": 2000000             # JSON size cap per response
    }

Dotted paths are plain data, never evaluated: each segment is an object key, or
a list index when it is a whole number (``items.0.name``). GET only, through the
guarded client (URL guard, robots.txt, per-host delay, conditional GET), with the
JSON size cap applied while the body streams. A next link is resolved against the
page it came from and must stay on the endpoint's host; it goes through the
guard again. Items without a title or a link that passes the URL guard are
dropped. Pagination stops early at an empty page or a repeated next link.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from urllib.parse import quote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from blackkite.collectors.base import CollectorError, RawItem
from blackkite.collectors.common import (
    MAX_SNIPPET,
    clean,
    html_text,
    http_link,
    parse_model,
    safe_url,
    utc_now,
)
from blackkite.collectors.http import FetchClient

DEFAULT_MAX_BYTES = 2_000_000
MAX_ITEMS_PER_PAGE = 500
_SEGMENT_MAX = 100
_PATH_HELP = "Dotted path into each item (for example buyer.name or tags.0)."

ParamValue = Annotated[str, Field(max_length=500)] | int | float | bool


def _check_path(v: str, allow_empty: bool = False) -> str:
    v = v.strip()
    if not v:
        if allow_empty:
            return v
        raise ValueError("path must not be empty")
    parts = v.split(".")
    if len(parts) > 10 or any(not p or len(p) > _SEGMENT_MAX for p in parts):
        raise ValueError(f"bad dotted path {v!r}")
    return v


def lookup(data: Any, path: str) -> Any:
    """Follow a dotted path; None when any step is missing."""
    if path == "":
        return data
    for part in path.split("."):
        if isinstance(data, dict):
            data = data.get(part)
        elif isinstance(data, list) and part.isdigit():
            i = int(part)
            data = data[i] if i < len(data) else None
        else:
            return None
        if data is None:
            return None
    return data


def _as_text(v: Any, limit: int) -> str | None:
    if isinstance(v, list):
        parts = [clean(x, limit) for x in v if not isinstance(x, dict | list)]
        return clean(", ".join(p for p in parts if p), limit)
    if isinstance(v, dict):
        return None
    return clean(v, limit)


class PagePagination(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["page"] = Field(description="Page number in a query parameter.")
    param: Annotated[str, Field(min_length=1, max_length=50)] = Field(
        default="page", description="Name of the page-number query parameter."
    )
    start: Annotated[int, Field(ge=0, le=1000)] = Field(
        default=1, description="Number of the first page."
    )
    max_pages: Annotated[int, Field(ge=1, le=20)] = Field(
        default=3, description="Pages to read per run."
    )


class NextLinkPagination(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["next_link"] = Field(
        description="Each response names the next page's address."
    )
    path: str = Field(
        description="Dotted path, in the whole response, to the next link."
    )
    max_pages: Annotated[int, Field(ge=1, le=20)] = Field(
        default=3, description="Pages to read per run."
    )

    @field_validator("path")
    @classmethod
    def _path(cls, v: str) -> str:
        return _check_path(v)


class FieldMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    list: str = Field(
        default="",
        description="Dotted path, in the whole response, to the array of items. "
        "Empty when the response itself is the array.",
    )
    title: str = Field(description=f"Title. {_PATH_HELP}")
    url: str = Field(
        description=f"Link to the notice, or an id for url_template. {_PATH_HELP}"
    )
    url_template: str | None = Field(
        default=None,
        description="Build the link from the url value: an address with {value} "
        "where the value goes.",
    )
    date: str | None = Field(default=None, description=f"Published date. {_PATH_HELP}")
    deadline: str | None = Field(default=None, description=f"Deadline. {_PATH_HELP}")
    organisation: str | None = Field(
        default=None, description=f"Issuing organisation. {_PATH_HELP}"
    )
    snippet: str | None = Field(
        default=None, description=f"Short description (HTML is stripped). {_PATH_HELP}"
    )
    extra: Annotated[dict[str, str], Field(max_length=10)] = Field(
        default={}, description="Other fields to keep: label -> dotted path."
    )

    @field_validator("list")
    @classmethod
    def _list(cls, v: str) -> str:
        return _check_path(v, allow_empty=True)

    @field_validator("title", "url", "date", "deadline", "organisation", "snippet")
    @classmethod
    def _paths(cls, v: str | None) -> str | None:
        return v if v is None else _check_path(v)

    @field_validator("extra")
    @classmethod
    def _extra(cls, v: dict[str, str]) -> dict[str, str]:
        out = {}
        for k, p in v.items():
            if not k.strip() or len(k) > 50:
                raise ValueError("extra labels must be 1-50 characters")
            out[k.strip()] = _check_path(p)
        return out

    @field_validator("url_template")
    @classmethod
    def _template(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if "{value}" not in v:
            raise ValueError("url_template must contain {value}")
        safe_url(v.replace("{value}", "x"))
        return v


class JsonApiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    endpoint: str = Field(description="Address of the JSON endpoint (GET).")
    params: Annotated[dict[str, ParamValue], Field(max_length=30)] = Field(
        default={}, description="Query parameters sent with every request."
    )
    pagination: PagePagination | NextLinkPagination | None = Field(
        default=None,
        discriminator="mode",
        description="Optional: how to reach later pages (page number or next link).",
    )
    mapping: FieldMapping = Field(description="Where each field is in the response.")
    max_bytes: Annotated[int, Field(ge=1000, le=5_000_000)] = Field(
        default=DEFAULT_MAX_BYTES, description="Largest response accepted, in bytes."
    )

    @field_validator("endpoint")
    @classmethod
    def _endpoint(cls, v: str) -> str:
        return safe_url(v)

    @field_validator("params")
    @classmethod
    def _params(cls, v: dict[str, Any]) -> dict[str, Any]:
        for k in v:
            if not k or len(k) > 100:
                raise ValueError("parameter names must be 1-100 characters")
        return v


def parse_config(config: dict[str, Any]) -> JsonApiConfig:
    return parse_model(JsonApiConfig, config, "json_api")


class JsonApiCollector:
    def __init__(
        self, client: FetchClient, *, preview: bool = False, now=utc_now
    ) -> None:
        self.client = client
        self.preview = preview
        self.now = now

    def _get_json(
        self, url: str, params: dict[str, Any] | None, cfg, delay
    ) -> tuple[Any, str]:
        resp = self.client.get(
            url,
            params=params,
            headers={"Accept": "application/json"},
            delay=delay,
            max_bytes=cfg.max_bytes,
        )
        try:
            return resp.json(), resp.url
        except RecursionError:
            raise CollectorError(f"JSON from {resp.url} is nested too deeply") from None

    def fetch(self, source) -> list[RawItem]:
        cfg = parse_config(source.config or {})
        pag = cfg.pagination
        max_pages = 1 if self.preview or pag is None else pag.max_pages
        host = (urlsplit(cfg.endpoint).hostname or "").lower()
        items: list[RawItem] = []
        seen: set[str] = set()
        url: str | None = cfg.endpoint
        visited: set[str] = set()
        for page in range(max_pages):
            params = {k: _param(v) for k, v in cfg.params.items()}
            if isinstance(pag, PagePagination):
                params[pag.param] = str(pag.start + page)
                url = cfg.endpoint
            elif page > 0:
                params = None  # a next link carries its own query string
            assert url is not None
            data, final_url = self._get_json(
                url, params or None, cfg, source.rate_limit
            )
            visited.add(final_url)
            rows = lookup(data, cfg.mapping.list)
            if not isinstance(rows, list):
                if page == 0:
                    raise CollectorError(
                        f"no array at {cfg.mapping.list or 'the top level'} "
                        f"in the response from {final_url}"
                    )
                break
            if not rows:
                break
            fetched_at = self.now()
            for row in rows[:MAX_ITEMS_PER_PAGE]:
                item = self._item(source, cfg, row, final_url, fetched_at)
                if item is not None and item.url not in seen:
                    seen.add(item.url)
                    items.append(item)
            if isinstance(pag, NextLinkPagination):
                nxt = http_link(final_url, lookup(data, pag.path))
                if nxt is None or nxt in visited:
                    break
                if (urlsplit(nxt).hostname or "").lower() != host:
                    raise CollectorError(
                        f"next link {nxt} leaves the endpoint's host {host}"
                    )
                url = nxt
        return items

    def _item(self, source, cfg: JsonApiConfig, row: Any, base: str, fetched_at):
        if not isinstance(row, dict):
            return None
        m = cfg.mapping
        title = html_text(_as_text(lookup(row, m.title), 1000), 500)
        raw_url = lookup(row, m.url)
        if m.url_template is not None:
            value = _as_text(raw_url, 300)
            link = (
                http_link(
                    None, m.url_template.replace("{value}", quote(value, safe=""))
                )
                if value
                else None
            )
        else:
            link = http_link(base, raw_url)
        if not title or not link:
            return None

        def pick(path: str | None, limit: int = 500) -> str | None:
            return None if path is None else _as_text(lookup(row, path), limit)

        snippet = pick(m.snippet, MAX_SNIPPET * 2)
        extra = {k: v for k, p in m.extra.items() if (v := pick(p))}
        return RawItem(
            source_id=source.id,
            url=link,
            title=title,
            fetched_at=fetched_at,
            organisation=pick(m.organisation),
            listed_published=pick(m.date, 100),
            listed_deadline=pick(m.deadline, 200),
            snippet=html_text(snippet, MAX_SNIPPET),
            extra=extra,
        )


def _param(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)
