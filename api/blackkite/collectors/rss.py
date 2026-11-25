"""``rss`` collector (spec 4.2): RSS 2.0, RSS 1.0 (RDF) and Atom feeds.

Config (``RssConfig``)::

    {
      "feed_url": "https://news.example/business/feed",
      "max_items": 50,                    # newest first, as the feed orders them
      "author_as_organisation": false     # see below
    }

The feed is fetched through the guarded client (URL guard, robots.txt, per-host
delay, size cap, conditional GET) and parsed with ``defusedxml``: entity
declarations (billion laughs) and external entities/DTDs are refused, so a
hostile feed cannot expand in memory or make us fetch anything.

Item -> RawItem:

- ``title``: <title> (HTML stripped); falls back to the start of the description.
- ``url``: RSS <link>, else a permalink <guid>; Atom <link rel="alternate">
  (or a link with no rel). Relative links are resolved against the feed URL;
  every link must pass the URL guard or the item is dropped.
- ``listed_published``: <pubDate> / <dc:date> / Atom <published>, else <updated>.
  RFC 822 dates with a zone are turned into ISO 8601 UTC; others kept as written.
- ``snippet``: <description> / Atom <summary>, else <content:encoded> / <content>,
  as plain text, at most 2000 characters.
- ``organisation``: None by default. In news feeds the author is a journalist,
  not the issuing organisation, and a wrong organisation hurts dedupe. Sources
  whose feed author IS the organisation (an issuer's own feed) can set
  ``author_as_organisation``. The author is always kept in ``extra["author"]``.
- ``extra``: ``author``, ``categories``, ``feed_title``, ``updated`` when present.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Annotated, Any

import defusedxml.ElementTree as DET
from defusedxml import DefusedXmlException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from blackkite.collectors.base import CollectorError, RawItem
from blackkite.collectors.common import (
    MAX_SNIPPET,
    clean,
    html_text,
    http_link,
    parse_model,
    rfc822_to_iso,
    safe_url,
    utc_now,
)
from blackkite.collectors.http import FetchClient

ATOM = "{http://www.w3.org/2005/Atom}"
RSS1 = "{http://purl.org/rss/1.0/}"
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
DC = "{http://purl.org/dc/elements/1.1/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"
PREVIEW_ITEMS = 20


class RssConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feed_url: str = Field(description="Address of the RSS or Atom feed.")
    max_items: Annotated[int, Field(ge=1, le=200)] = Field(
        default=50, description="Read at most this many items per run (1-200)."
    )
    author_as_organisation: bool = Field(
        default=False,
        description="Use the item author as the issuing organisation. Only for "
        "feeds published by the issuer itself; leave off for news feeds.",
    )

    @field_validator("feed_url")
    @classmethod
    def _feed_url(cls, v: str) -> str:
        return safe_url(v)


def parse_config(config: dict[str, Any]) -> RssConfig:
    return parse_model(RssConfig, config, "rss")


# --- parsing ------------------------------------------------------------------------


def _text(el: ET.Element | None) -> str | None:
    if el is None:
        return None
    return "".join(el.itertext())


def _first(el: ET.Element, *tags: str) -> str | None:
    for tag in tags:
        value = _text(el.find(tag))
        if value is not None and value.strip():
            return value
    return None


def _rss_author(value: str | None) -> str | None:
    # RSS 2.0 <author> is "email (Name)"; keep the name when there is one.
    value = clean(value, 200)
    if value and value.endswith(")") and "(" in value:
        return value[value.index("(") + 1 : -1].strip() or value
    return value


def _atom_link(entry: ET.Element, base: str) -> str | None:
    fallback = None
    for link in entry.findall(f"{ATOM}link"):
        rel = (link.get("rel") or "alternate").strip()
        href = http_link(base, link.get("href"))
        if href is None:
            continue
        if rel == "alternate":
            return href
        fallback = fallback or (href if rel in ("related", "via") else None)
    return fallback


def _guid_link(item: ET.Element, base: str) -> str | None:
    guid = item.find("guid")
    if guid is None or (guid.get("isPermaLink") or "true").lower() == "false":
        return None
    return http_link(base, _text(guid))


def _parse_xml(content: bytes, url: str) -> ET.Element:
    try:
        return DET.fromstring(
            content, forbid_dtd=False, forbid_entities=True, forbid_external=True
        )
    except DefusedXmlException as e:
        raise CollectorError(f"feed {url} refused: {type(e).__name__}") from None
    except (ET.ParseError, ValueError) as e:
        raise CollectorError(f"feed {url} is not well-formed XML: {e}") from None


def parse_feed(content: bytes, feed_url: str) -> list[dict[str, Any]]:
    """Feed bytes -> list of item dicts (title, url, published, snippet, author,
    extra). Raises CollectorError for anything that is not RSS or Atom."""
    root = _parse_xml(content, feed_url)
    out: list[dict[str, Any]] = []
    if root.tag == f"{ATOM}feed":
        feed_title = clean(_first(root, f"{ATOM}title"), 200)
        for e in root.findall(f"{ATOM}entry"):
            summary = _first(e, f"{ATOM}summary") or _first(e, f"{ATOM}content")
            authors = [
                a
                for a in (
                    clean(_text(x.find(f"{ATOM}name")), 200)
                    for x in e.findall(f"{ATOM}author")
                )
                if a
            ]
            cats = [
                c.get("term") or c.get("label") or ""
                for c in e.findall(f"{ATOM}category")
            ]
            out.append(
                {
                    "title": _first(e, f"{ATOM}title"),
                    "url": _atom_link(e, feed_url),
                    "published": _first(e, f"{ATOM}published"),
                    "updated": _first(e, f"{ATOM}updated"),
                    "summary": summary,
                    "author": ", ".join(authors) or None,
                    "categories": cats,
                    "feed_title": feed_title,
                }
            )
        return out
    if root.tag == "rss":
        channel = root.find("channel")
        if channel is None:
            raise CollectorError(f"feed {feed_url} has no <channel>")
        items = channel.findall("item")
        feed_title = clean(_first(channel, "title"), 200)
        rss1 = False
    elif root.tag == f"{RDF}RDF":
        channel = root.find(f"{RSS1}channel")
        items = root.findall(f"{RSS1}item")
        feed_title = (
            clean(_first(channel, f"{RSS1}title"), 200) if channel is not None else None
        )
        rss1 = True
    else:
        raise CollectorError(f"{feed_url} is not an RSS or Atom feed")
    for it in items:
        if rss1:
            link = http_link(feed_url, _first(it, f"{RSS1}link"))
            title = _first(it, f"{RSS1}title")
            summary = _first(it, f"{RSS1}description", f"{CONTENT}encoded")
        else:
            link = http_link(feed_url, _first(it, "link")) or _guid_link(it, feed_url)
            title = _first(it, "title")
            summary = _first(it, "description", f"{CONTENT}encoded")
        out.append(
            {
                "title": title,
                "url": link,
                "published": _first(it, "pubDate", f"{DC}date"),
                "updated": None,
                "summary": summary,
                "author": _rss_author(_first(it, "author", f"{DC}creator")),
                "categories": [_text(c) or "" for c in it.findall("category")]
                + [_text(c) or "" for c in it.findall(f"{DC}subject")],
                "feed_title": feed_title,
            }
        )
    return out


class RssCollector:
    def __init__(
        self, client: FetchClient, *, preview: bool = False, now=utc_now
    ) -> None:
        self.client = client
        self.preview = preview
        self.now = now

    def fetch(self, source) -> list[RawItem]:
        cfg = parse_config(source.config or {})
        resp = self.client.get(cfg.feed_url, delay=source.rate_limit)
        entries = parse_feed(resp.content, resp.url)
        limit = min(cfg.max_items, PREVIEW_ITEMS) if self.preview else cfg.max_items
        fetched_at: datetime = self.now()
        items: list[RawItem] = []
        seen: set[str] = set()
        for e in entries:
            if len(items) >= limit:
                break
            url = e["url"]
            snippet = html_text(e["summary"], MAX_SNIPPET)
            title = html_text(e["title"], 500) or clean(snippet, 150)
            if not url or not title or url in seen:
                continue
            seen.add(url)
            extra: dict[str, str] = {}
            for key in ("author", "feed_title"):
                if e.get(key):
                    extra[key] = e[key]
            if e.get("updated"):
                extra["updated"] = rfc822_to_iso(e["updated"]) or ""
            cats = [c for c in (clean(c, 100) for c in e["categories"]) if c]
            if cats:
                extra["categories"] = ", ".join(dict.fromkeys(cats))[:500]
            items.append(
                RawItem(
                    source_id=source.id,
                    url=url,
                    title=title,
                    fetched_at=fetched_at,
                    organisation=e["author"] if cfg.author_as_organisation else None,
                    listed_published=rfc822_to_iso(e["published"] or e["updated"]),
                    snippet=snippet,
                    extra={k: v for k, v in extra.items() if v},
                )
            )
        return items
