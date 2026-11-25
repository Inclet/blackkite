"""Small helpers shared by the collector types added in M3."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin

from pydantic import BaseModel, ValidationError
from selectolax.lexbor import LexborHTMLParser

from blackkite.collectors.base import CollectorError
from blackkite.collectors.problems import ConfigInvalid, from_validation
from blackkite.sources.urlsafety import UnsafeURL, check_url

MAX_FIELD = 500
MAX_SNIPPET = 2000
_WS = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?)])")


def parse_model[M: BaseModel](
    model: type[M], config: dict[str, Any], collector_type: str
) -> M:
    """Validate a source config; CollectorError with a readable message if bad."""
    if config.get("placeholder"):
        raise CollectorError(
            "source config is a placeholder; set it after the M0 access test"
        )
    try:
        return model.model_validate(config)
    except ValidationError as e:
        raise ConfigInvalid(collector_type, from_validation(e)) from None


def safe_url(v: str) -> str:
    """Pydantic validator body: the URL guard's syntactic check."""
    try:
        check_url(v)
    except UnsafeURL as e:
        raise ValueError(str(e)) from None
    return v


def http_link(base: str | None, href: Any) -> str | None:
    """Absolute http(s) URL that passes the URL guard, or None."""
    if not isinstance(href, str) or not href.strip():
        return None
    url = urljoin(base, href.strip()) if base else href.strip()
    try:
        check_url(url)
    except UnsafeURL:
        return None
    return url


def clean(text: Any, limit: int = MAX_FIELD) -> str | None:
    if text is None or isinstance(text, bool):
        return None
    if isinstance(text, int | float):
        text = str(text)
    if not isinstance(text, str):
        return None
    text = _WS.sub(" ", text).strip()
    return text[:limit] or None


def html_text(markup: str | None, limit: int = MAX_SNIPPET) -> str | None:
    """Visible text of an HTML fragment (feed descriptions, email bodies)."""
    if not markup:
        return None
    if "<" not in markup and "&" not in markup:
        return clean(markup, limit)
    tree = LexborHTMLParser(markup)
    for node in tree.css("script, style, noscript, template"):
        node.decompose()
    root = tree.body or tree.root
    if root is None:
        return None
    text = clean(root.text(separator=" "), limit * 2)
    return clean(_SPACE_BEFORE_PUNCT.sub(r"\1", text), limit) if text else None


def rfc822_to_iso(text: str | None) -> str | None:
    """'Tue, 24 Nov 2026 10:00:00 +0000' -> '2026-11-24T10:00:00+00:00'. Anything
    else is returned cleaned and unchanged (the validate stage parses it)."""
    text = clean(text, 100)
    if text is None:
        return None
    try:
        d = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return text
    if d.tzinfo is None:
        return text  # no zone stated: leave it to the validate stage (Kigali time)
    return d.astimezone(UTC).isoformat()


def utc_now() -> datetime:
    return datetime.now(UTC)
