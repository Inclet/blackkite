"""Stage 2, normalise: canonical URL, cleaned title and organisation, raw text.

Nothing here touches the database or the network.
"""

from __future__ import annotations

import html
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from blackkite.collectors.base import RawItem

# Query parameters that only track the click, never select the content.
TRACKING_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "gbraid",
        "wbraid",
        "msclkid",
        "yclid",
        "twclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "_ga",
        "_gl",
        "_hsenc",
        "_hsmi",
        "mkt_tok",
        "oly_anon_id",
        "oly_enc_id",
        "vero_id",
        "spm",
    }
)
TRACKING_PREFIXES = ("utm_", "pk_", "hsa_")

DEFAULT_PORTS = {"http": 80, "https": 443}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# Separators and labels left at the edges of organisation names by listing pages.
_ORG_EDGE = " \t-–—|:;,·•"
_ORG_LABEL_RE = re.compile(
    r"^(?:by|organi[sz]ation|organi[sz]er|procuring entity|client|issuer|publisher)\s*:\s*",
    re.IGNORECASE,
)


def canonical_url(url: str) -> str:
    """Canonical form used as the exact-match key for dedupe.

    Lowercase scheme and host, default port dropped, fragment dropped, tracking
    parameters removed, remaining parameters sorted (stable order), empty path -> "/",
    and no trailing slash on any other path ("/a/b/" -> "/a/b").
    """
    raw = url.strip()
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not scheme or not host:
        return raw
    netloc = host
    if ":" in host:  # IPv6 literal
        netloc = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    if port is not None and DEFAULT_PORTS.get(scheme) != port:
        netloc = f"{netloc}:{port}"
    # Credentials in a listing URL are never meaningful; they are dropped.
    path = parts.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/") or "/"
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
        and not k.lower().startswith(TRACKING_PREFIXES)
    ]
    query.sort()
    return urlunsplit((scheme, netloc, path, urlencode(query, doseq=True), ""))


def clean_text(value: str | None) -> str | None:
    """Unescape HTML entities, drop tags, collapse whitespace. Casing untouched."""
    if value is None:
        return None
    text = html.unescape(value)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)  # entities that were double-escaped (&amp;amp;)
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    text = _WS_RE.sub(" ", text).strip()
    return text or None


def clean_title(value: str) -> str:
    return clean_text(value) or ""


def clean_organisation(value: str | None) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    text = _ORG_LABEL_RE.sub("", text)
    text = text.strip(_ORG_EDGE)
    return text or None


@dataclass(frozen=True, slots=True)
class NormalisedItem:
    source_id: uuid.UUID
    url: str  # canonical
    detail_url: str | None  # canonical
    title: str
    organisation: str | None
    listed_published: str | None
    listed_deadline: str | None
    snippet: str | None
    raw_text: str  # what the listing said, as one block of text
    fetched_at: datetime
    extra: dict[str, str]


def raw_text_of(item: RawItem) -> str:
    lines = [clean_title(item.title)]
    for label, value in (
        ("Organisation", clean_organisation(item.organisation)),
        ("Published", clean_text(item.listed_published)),
        ("Deadline", clean_text(item.listed_deadline)),
    ):
        if value:
            lines.append(f"{label}: {value}")
    snippet = clean_text(item.snippet)
    if snippet:
        lines.append(snippet)
    for key, value in sorted(item.extra.items()):
        cleaned = clean_text(value)
        if cleaned:
            lines.append(f"{key}: {cleaned}")
    return "\n".join(lines)


def normalise(item: RawItem) -> NormalisedItem:
    detail = canonical_url(item.detail_url) if item.detail_url else None
    url = canonical_url(item.url)
    return NormalisedItem(
        source_id=item.source_id,
        url=url,
        detail_url=detail if detail != url else None,
        title=clean_title(item.title),
        organisation=clean_organisation(item.organisation),
        listed_published=clean_text(item.listed_published),
        listed_deadline=clean_text(item.listed_deadline),
        snippet=clean_text(item.snippet),
        raw_text=raw_text_of(item),
        fetched_at=item.fetched_at,
        extra=dict(item.extra),
    )
