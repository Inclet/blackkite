"""``html_list`` collector (spec 4.2): server-rendered listing pages, CSS selectors.

Config (validated by ``HtmlListConfig``; selectors are data handed to the CSS engine,
never evaluated as code; the pagination pattern is filled by plain string
replacement of ``{page}``, not ``str.format``)::

    {
      "list_url": "https://example.org/tenders",
      "pagination_pattern": "https://example.org/tenders?page={page}",   # optional
      "first_page": 2,            # page number of the first pattern page (default 2)
      "max_pages": 3,             # list_url counts as page 1 (default 1)
      "selectors": {
        "item": "article.notice",                   # required: one node per listing
        "title": "h3",                              # required
        "link": {"css": "h3 a", "attr": "href"},    # default: <a> in/at title, or item
        "date": ".published",                       # -> RawItem.listed_published
        "deadline": ".closing",                     # -> RawItem.listed_deadline
        "organisation": ".org",
        "snippet": ".summary"
      },
      "detail": {                                   # optional: follow each link
        "selectors": {"deadline": ".deadline", "organisation": ".buyer",
                      "date": ".date", "snippet": ".body"},
        "max_items": 20
      }
    }

A selector is a CSS string (text of the first match) or ``{"css": ..., "attr": ...}``.
Detail-page values take precedence over the listing (the notice itself is the better
record, spec 2.3); a failed detail page keeps the listing values and records the
error in ``extra["detail_error"]``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import urljoin

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from selectolax.lexbor import LexborHTMLParser, LexborNode, SelectolaxError

from blackkite.collectors.base import CollectorError, RawItem
from blackkite.collectors.http import FetchClient
from blackkite.sources.urlsafety import UnsafeURL, check_url

PREVIEW_DETAIL_ITEMS = 3
MAX_SNIPPET = 2000
MAX_FIELD = 500
_WS = re.compile(r"\s+")


def _check_css(css: str) -> str:
    css = css.strip()
    if not css or len(css) > 500:
        raise ValueError("selector must be 1-500 characters")
    try:
        LexborHTMLParser("<p></p>").css(css)
    except SelectolaxError as e:
        raise ValueError(f"invalid CSS selector {css!r}: {e}") from None
    return css


class Sel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    css: str = Field(
        description="CSS selector; the first match inside the item is used."
    )
    attr: Annotated[str, Field(pattern=r"^[A-Za-z_:][-A-Za-z0-9_:.]{0,60}$")] | None = (
        Field(
            default=None,
            description="Read this attribute instead of the text (for example href).",
        )
    )

    @field_validator("css")
    @classmethod
    def _css(cls, v: str) -> str:
        return _check_css(v)


def _sel(v: Any) -> Any:
    return {"css": v} if isinstance(v, str) else v


_SEL_HELP = "A CSS selector, or {css, attr} to read an attribute."


class ListSelectors(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(description="CSS selector matching one node per listing.")
    title: Sel = Field(description=f"Title inside the item. {_SEL_HELP}")
    link: Sel | None = Field(
        default=None,
        description="Link to the notice (default: the <a> in or at the title, "
        f"else in the item). {_SEL_HELP}",
    )
    date: Sel | None = Field(
        default=None, description=f"Published date as listed. {_SEL_HELP}"
    )
    deadline: Sel | None = Field(
        default=None, description=f"Deadline as listed. {_SEL_HELP}"
    )
    organisation: Sel | None = Field(
        default=None, description=f"Issuing organisation. {_SEL_HELP}"
    )
    snippet: Sel | None = Field(
        default=None, description=f"Short description text. {_SEL_HELP}"
    )

    @field_validator("item")
    @classmethod
    def _item(cls, v: str) -> str:
        return _check_css(v)

    @field_validator(
        "title", "link", "date", "deadline", "organisation", "snippet", mode="before"
    )
    @classmethod
    def _wrap(cls, v: Any) -> Any:
        return _sel(v)


class DetailSelectors(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: Sel | None = Field(
        default=None, description=f"Published date on the detail page. {_SEL_HELP}"
    )
    deadline: Sel | None = Field(
        default=None, description=f"Deadline on the detail page. {_SEL_HELP}"
    )
    organisation: Sel | None = Field(
        default=None, description=f"Organisation on the detail page. {_SEL_HELP}"
    )
    snippet: Sel | None = Field(
        default=None, description=f"Notice text on the detail page. {_SEL_HELP}"
    )

    @field_validator("date", "deadline", "organisation", "snippet", mode="before")
    @classmethod
    def _wrap(cls, v: Any) -> Any:
        return _sel(v)


class DetailConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selectors: DetailSelectors = Field(
        description="Selectors applied to each item's detail page; values found "
        "there replace the listing's."
    )
    max_items: Annotated[int, Field(ge=1, le=50)] = Field(
        default=20, description="Follow at most this many detail pages per run."
    )


def _url_ok(v: str) -> str:
    try:
        check_url(v)
    except UnsafeURL as e:
        raise ValueError(str(e)) from None
    return v


class HtmlListConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    list_url: str = Field(description="Address of the listing page (page 1).")
    pagination_pattern: str | None = Field(
        default=None,
        description="Address of later pages with {page} where the number goes.",
    )
    first_page: Annotated[int, Field(ge=0, le=1000)] = Field(
        default=2, description="Page number of the first pattern page."
    )
    max_pages: Annotated[int, Field(ge=1, le=20)] = Field(
        default=1, description="Pages to read per run, counting list_url as 1."
    )
    selectors: ListSelectors = Field(description="Where each field is on the list.")
    detail: DetailConfig | None = Field(
        default=None, description="Optional: follow each link to its detail page."
    )

    @field_validator("list_url")
    @classmethod
    def _list_url(cls, v: str) -> str:
        return _url_ok(v)

    @field_validator("pagination_pattern")
    @classmethod
    def _pattern(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if "{page}" not in v:
            raise ValueError("pagination_pattern must contain {page}")
        _url_ok(v.replace("{page}", "1"))
        return v

    def page_urls(self) -> list[str]:
        urls = [self.list_url]
        if self.pagination_pattern:
            for i in range(self.max_pages - 1):
                urls.append(
                    self.pagination_pattern.replace("{page}", str(self.first_page + i))
                )
        return urls


def parse_config(config: dict[str, Any]) -> HtmlListConfig:
    if config.get("placeholder"):
        raise CollectorError(
            "source config is a placeholder; set it after the M0 access test"
        )
    try:
        return HtmlListConfig.model_validate(config)
    except ValidationError as e:
        raise CollectorError(f"invalid html_list config: {e}") from None


def _clean(text: str | None, limit: int = MAX_FIELD) -> str | None:
    if text is None:
        return None
    text = _WS.sub(" ", text).strip()
    return text[:limit] or None


def _value(root: LexborNode, sel: Sel | None, limit: int = MAX_FIELD) -> str | None:
    if sel is None:
        return None
    node = root.css_first(sel.css)
    if node is None:
        return None
    if sel.attr:
        return _clean(node.attributes.get(sel.attr), limit)
    return _clean(node.text(separator=" "), limit)


def _http_link(base: str, href: str | None) -> str | None:
    if not href:
        return None
    url = urljoin(base, href.strip())
    return url if url.lower().startswith(("http://", "https://")) else None


def _link(item: LexborNode, sels: ListSelectors, base: str) -> str | None:
    if sels.link is not None:
        node = item.css_first(sels.link.css)
        if node is None:
            return None
        return _http_link(base, node.attributes.get(sels.link.attr or "href"))
    title = item.css_first(sels.title.css)
    for node in (title, item):
        if node is None:
            continue
        if node.tag == "a":
            return _http_link(base, node.attributes.get("href"))
        a = node.css_first("a[href]")
        if a is not None:
            return _http_link(base, a.attributes.get("href"))
    return None


def _parse(html: str, css: str) -> list[LexborNode]:
    try:
        return LexborHTMLParser(html).css(css)
    except SelectolaxError as e:
        raise CollectorError(f"cannot apply selector {css!r}: {e}") from None


class HtmlListCollector:
    def __init__(
        self,
        client: FetchClient,
        *,
        preview: bool = False,
        now=lambda: datetime.now(UTC),
    ) -> None:
        self.client = client
        self.preview = preview
        self.now = now

    def fetch(self, source) -> list[RawItem]:
        cfg = parse_config(source.config or {})
        pages = cfg.page_urls()[:1] if self.preview else cfg.page_urls()
        items: list[RawItem] = []
        seen: set[str] = set()
        for page_url in pages:
            resp = self.client.get(page_url, delay=source.rate_limit)
            nodes = _parse(resp.text, cfg.selectors.item)
            if not nodes and page_url != pages[0]:
                break  # ran past the last page
            fetched_at = self.now()
            for node in nodes:
                title = _value(node, cfg.selectors.title)
                link = _link(node, cfg.selectors, resp.url)
                if not title or not link or link in seen:
                    continue
                seen.add(link)
                items.append(
                    RawItem(
                        source_id=source.id,
                        url=link,
                        title=title,
                        fetched_at=fetched_at,
                        organisation=_value(node, cfg.selectors.organisation),
                        listed_published=_value(node, cfg.selectors.date),
                        listed_deadline=_value(node, cfg.selectors.deadline),
                        snippet=_value(node, cfg.selectors.snippet, MAX_SNIPPET),
                        extra={"list_page": resp.url},
                    )
                )
        if cfg.detail is not None:
            limit = PREVIEW_DETAIL_ITEMS if self.preview else cfg.detail.max_items
            items = [
                self._with_detail(it, cfg.detail.selectors, source.rate_limit)
                if i < limit
                else it
                for i, it in enumerate(items)
            ]
        return items

    def _with_detail(
        self, item: RawItem, sels: DetailSelectors, delay: float | None
    ) -> RawItem:
        extra = dict(item.extra)
        try:
            resp = self.client.get(item.url, delay=delay)
            root = LexborHTMLParser(resp.text).body
        except CollectorError as e:
            extra["detail_error"] = str(e)[:500]
            return _replace(item, extra=extra)
        if root is None:
            return _replace(item, detail_url=item.url, extra=extra)

        def pick(sel: Sel | None, current: str | None, limit=MAX_FIELD) -> str | None:
            return _value(root, sel, limit) or current

        return _replace(
            item,
            detail_url=resp.url,
            organisation=pick(sels.organisation, item.organisation),
            listed_published=pick(sels.date, item.listed_published),
            listed_deadline=pick(sels.deadline, item.listed_deadline),
            snippet=pick(sels.snippet, item.snippet, MAX_SNIPPET),
            extra=extra,
        )


def _replace(item: RawItem, **changes: Any) -> RawItem:
    from dataclasses import replace

    return replace(item, **changes)
