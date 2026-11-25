"""Stage 4, enrich: follow the detail page, fetch attached PDFs, extract their text.

Fetching goes through an injected ``Fetcher``. The fetcher owns politeness and safety:
robots.txt, the source's rate limit, an honest User-Agent, no aggressive retries,
and refusing internal network addresses (spec 10). This module only ever asks it
for http(s) URLs and never follows more than ``documents_per_item`` attachments.

Downloaded files are kept under ``<data_dir>/documents`` for extraction and the
owner's reference. They are never served to members (spec 10).
"""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlsplit

from blackkite.pipeline.normalise import canonical_url

log = logging.getLogger("blackkite.pipeline.enrich")

MAX_PDF_PAGES = 100
MAX_TEXT_CHARS = 500_000


class Fetcher(Protocol):
    """GET a URL; return (content type, body). Raise on any failure."""

    def get(self, url: str) -> tuple[str, bytes]: ...


@dataclass
class FetchedDocument:
    url: str
    content_type: str
    file_path: str | None
    text: str | None


@dataclass
class Enrichment:
    detail: FetchedDocument | None = None
    attachments: list[FetchedDocument] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def documents(self) -> list[FetchedDocument]:
        return ([self.detail] if self.detail else []) + self.attachments

    def text(self) -> str:
        parts = [d.text for d in self.documents if d.text]
        return "\n\n".join(parts)


# --- HTML to text -------------------------------------------------------------------

_SKIP = {"script", "style", "noscript", "template", "svg", "head", "iframe", "form"}
_BLOCK = {
    "p",
    "div",
    "br",
    "li",
    "tr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "section",
    "article",
    "table",
    "ul",
    "ol",
    "dt",
    "dd",
    "header",
    "footer",
}


class _TextAndLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[tuple[str, str | None]] = []  # (href, type attribute)
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")
        if tag == "a":
            a = dict(attrs)
            if a.get("href"):
                self.links.append((a["href"], a.get("type")))

    def handle_endtag(self, tag):
        if tag in _SKIP and self._skip:
            self._skip -= 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(content: bytes) -> tuple[str, list[tuple[str, str | None]]]:
    parser = _TextAndLinks()
    parser.feed(content.decode("utf-8", errors="replace"))
    parser.close()
    lines = []
    for line in "".join(parser.parts).splitlines():
        line = " ".join(line.split())
        if line:
            lines.append(line)
    return "\n".join(lines)[:MAX_TEXT_CHARS], parser.links


def pdf_to_text(content: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    texts = []
    for page in reader.pages[:MAX_PDF_PAGES]:
        texts.append(page.extract_text() or "")
    return "\n".join(t.strip() for t in texts if t.strip())[:MAX_TEXT_CHARS]


def is_pdf(content_type: str, content: bytes) -> bool:
    return "pdf" in content_type.lower() or content[:5] == b"%PDF-"


def is_html(content_type: str, content: bytes) -> bool:
    ct = content_type.lower()
    if "html" in ct or "xml" in ct:
        return True
    return not ct and content.lstrip()[:1] == b"<"


def pdf_links(base_url: str, links: list[tuple[str, str | None]]) -> list[str]:
    seen: list[str] = []
    for href, typ in links:
        url = urljoin(base_url, href.strip())
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            continue
        if parts.path.lower().endswith(".pdf") or (typ and "pdf" in typ.lower()):
            url = canonical_url(url)
            if url not in seen:
                seen.append(url)
    return seen


# --- Storage -----------------------------------------------------------------------


def store_file(data_dir: Path, content: bytes, suffix: str) -> str:
    digest = hashlib.sha256(content).hexdigest()
    path = data_dir / "documents" / digest[:2] / f"{digest}{suffix}"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(content)
        tmp.replace(path)
    return str(path)


# --- Stage --------------------------------------------------------------------------


def _fetch(
    fetcher: Fetcher, url: str, *, data_dir: Path, max_bytes: int, errors: list[str]
) -> tuple[FetchedDocument, list[tuple[str, str | None]]] | None:
    if urlsplit(url).scheme not in ("http", "https"):
        errors.append(f"not fetched (scheme): {url}")
        return None
    try:
        content_type, content = fetcher.get(url)
    # Any fetcher failure (its exception types are its own) is this item's problem,
    # never the run's.
    except Exception as exc:  # noqa: BLE001
        errors.append(f"fetch failed: {url}: {type(exc).__name__}: {exc}")
        return None
    if len(content) > max_bytes:
        errors.append(f"not kept (over {max_bytes} bytes): {url}")
        return None
    try:
        if is_pdf(content_type, content):
            text, links = pdf_to_text(content), []
            suffix = ".pdf"
        elif is_html(content_type, content):
            text, links = html_to_text(content)
            suffix = ".html"
        else:
            errors.append(f"not kept (content type {content_type!r}): {url}")
            return None
    except Exception as exc:  # noqa: BLE001 - malformed files raise anything
        errors.append(f"text extraction failed: {url}: {type(exc).__name__}: {exc}")
        text, links, suffix = None, [], ".bin"
    path = store_file(data_dir, content, suffix)
    return FetchedDocument(url, content_type, path, text or None), links


def enrich(
    fetcher: Fetcher | None,
    url: str,
    *,
    data_dir: Path,
    max_bytes: int,
    max_attachments: int,
) -> Enrichment:
    """Fetch ``url`` (the detail page) and up to ``max_attachments`` linked PDFs."""
    out = Enrichment()
    if fetcher is None:
        out.errors.append("no fetcher configured; detail page not followed")
        return out
    got = _fetch(
        fetcher, url, data_dir=data_dir, max_bytes=max_bytes, errors=out.errors
    )
    if got is None:
        return out
    out.detail, links = got
    for pdf in pdf_links(url, links)[:max_attachments]:
        if pdf == url:
            continue
        doc = _fetch(
            fetcher, pdf, data_dir=data_dir, max_bytes=max_bytes, errors=out.errors
        )
        if doc is not None:
            out.attachments.append(doc[0])
    for e in out.errors:
        log.info("enrich %s: %s", url, e)
    return out
