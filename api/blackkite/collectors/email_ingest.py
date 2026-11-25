"""``email_ingest`` collector (spec 4.2): newsletters and alert emails in a shared
inbox, read over IMAP.

Config (``EmailIngestConfig``; nothing secret)::

    {
      "sender": "*@alerts.example.org",     # address, or a glob pattern (* and ?)
      "subject_pattern": "*tender*",        # optional glob, case-insensitive
      "parse_mode": "links",                # "links": every link in the body is an
                                            #   item; "message": one item per email
      "link_pattern": "https://board.example/job/*",   # optional glob on links
      "min_title_chars": 12,                # links mode: shorter anchor texts skipped
      "folder": "INBOX",
      "since_days": 14,                     # only look at mail this recent
      "max_messages": 50,
      "require_authenticated": true         # see "Spoofing" below
    }

The mailbox comes from the environment only: ``BK_INGEST_IMAP_HOST``,
``BK_INGEST_IMAP_PORT`` (993), ``BK_INGEST_IMAP_USER``,
``BK_INGEST_IMAP_PASSWORD``. IMAP over TLS with certificate checks; no plain
IMAP. The host is operator configuration, not admin input, so it is not put
through the public-address guard (a mail server on the VPS's private network is
legitimate).

Processed messages. No table: the state lives on the server. After a scheduled
run, every message this source matched and read is flagged with a keyword of its
own (``BkDone<first 12 hex of the source id>``), so sources sharing the inbox do
not hide mail from one another; if the server does not accept custom keywords
(no ``\\*`` in PERMANENTFLAGS) ``\\Seen`` is used instead. Each run searches
``SINCE <since_days ago>`` without that flag. Messages are read with
``BODY.PEEK[]`` (reading alone never marks them). A test run (preview) opens the
folder read-only and flags nothing.

Flags are set only once the run is safe: ``fetch`` remembers which messages it
read, and the runner calls ``after_commit(source)`` after it has committed the
ingest (worker/runner.py). That opens the mailbox again and flags them. If the
ingest fails and is rolled back, ``after_commit`` is never called and the same
mail is read again on the next run. If the folder's UIDVALIDITY changed in
between (the mailbox was rebuilt), nothing is flagged: re-reading is harmless,
the ingest dedupes, but flagging the wrong messages would hide mail.

Spoofing. Anyone can send mail to the shared inbox with any From, and can put
any ``Authentication-Results`` header in it. With ``require_authenticated``
(default) a message counts only if the topmost ``Authentication-Results`` header
whose authserv-id equals ``BK_INGEST_AUTHSERV_ID`` (the receiving server's own
id, RFC 8601) reports ``dmarc=pass`` for the From domain, or ``dkim=pass`` with
``header.d`` equal to (or a parent of) the From domain. Headers with any other
authserv-id are ignored. Without ``BK_INGEST_AUTHSERV_ID`` such a source refuses
to run (CollectorError) rather than trust a header anyone could have written.

Links found in mail pass ``check_url`` (http/https, no credentials, no internal
addresses) before they become items; nothing in a message is fetched here.
"""

from __future__ import annotations

import email
import email.policy
import fnmatch
import imaplib
import logging
import re
import ssl
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from selectolax.lexbor import LexborHTMLParser, LexborNode

from blackkite.collectors.base import CollectorError, RawItem
from blackkite.collectors.common import (
    MAX_SNIPPET,
    clean,
    html_text,
    http_link,
    parse_model,
    rfc822_to_iso,
    utc_now,
)

log = logging.getLogger("blackkite.collectors")

MAX_MESSAGE_BYTES = 2_000_000
MAX_LINKS_PER_MESSAGE = 200
_IMAP_SAFE = re.compile(r'^[^"\\\x00-\x1f\x7f]+$')
_TEXT_URL = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
_MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]


# --- settings and mailbox -------------------------------------------------------------


class ImapSettings(BaseSettings):
    """The shared ingest inbox. Environment only (BK_INGEST_IMAP_*)."""

    model_config = SettingsConfigDict(
        env_prefix="BK_INGEST_IMAP_", env_file=".env", extra="ignore"
    )
    host: str | None = None
    port: int = 993
    user: str | None = None
    password: SecretStr | None = None
    timeout_seconds: float = 30.0


class Mailbox(Protocol):
    """The IMAP operations the collector uses (UIDs as strings). A mailbox may
    also have ``uid_validity() -> str | None`` for the selected folder; without
    it, UIDs are trusted to be stable between fetch and after_commit."""

    def select(self, folder: str, *, readonly: bool) -> None: ...
    def supports_keywords(self) -> bool: ...
    def search(self, criteria: list[str]) -> list[str]: ...
    def size(self, uid: str) -> int | None: ...
    def fetch(self, uid: str) -> bytes: ...
    def add_flag(self, uids: list[str], flag: str) -> None: ...
    def logout(self) -> None: ...


class ImapMailbox:
    """``Mailbox`` over ``imaplib.IMAP4_SSL`` with a verifying TLS context."""

    def __init__(self, settings: ImapSettings, *, imap_class=imaplib.IMAP4_SSL) -> None:
        if not (settings.host and settings.user and settings.password):
            raise CollectorError(
                "no ingest mailbox configured (BK_INGEST_IMAP_HOST, "
                "BK_INGEST_IMAP_USER, BK_INGEST_IMAP_PASSWORD)"
            )
        try:
            self.imap = imap_class(
                settings.host,
                settings.port,
                ssl_context=ssl.create_default_context(),
                timeout=settings.timeout_seconds,
            )
            self.imap.login(settings.user, settings.password.get_secret_value())
        except (OSError, imaplib.IMAP4.error) as e:
            raise CollectorError(f"cannot open the ingest mailbox: {e}") from None
        self._keywords = False
        self._uid_validity: str | None = None

    def _ok(self, typ: str, data: Any, what: str) -> Any:
        if typ != "OK":
            raise CollectorError(f"IMAP {what} failed: {data!r}"[:300])
        return data

    def _call(self, what: str, fn: Callable[..., tuple[str, Any]], *args) -> Any:
        try:
            typ, data = fn(*args)
        except (OSError, imaplib.IMAP4.error) as e:
            raise CollectorError(f"IMAP {what} failed: {e}") from None
        return self._ok(typ, data, what)

    def select(self, folder: str, *, readonly: bool) -> None:
        self._call("select", self.imap.select, f'"{folder}"', readonly)
        _, flags = self.imap.response("PERMANENTFLAGS")
        text = b" ".join(f for f in flags or [] if isinstance(f, bytes))
        self._keywords = b"\\*" in text
        _, validity = self.imap.response("UIDVALIDITY")
        found = [v for v in validity or [] if isinstance(v, bytes)]
        self._uid_validity = found[0].decode(errors="replace") if found else None

    def uid_validity(self) -> str | None:
        """UIDVALIDITY of the selected folder, when the server sent it."""
        return self._uid_validity

    def supports_keywords(self) -> bool:
        return self._keywords

    def search(self, criteria: list[str]) -> list[str]:
        data = self._call("search", self.imap.uid, "SEARCH", *criteria)
        return [u.decode() for u in (data[0] or b"").split()]

    def size(self, uid: str) -> int | None:
        data = self._call("fetch", self.imap.uid, "FETCH", uid, "(RFC822.SIZE)")
        m = re.search(rb"RFC822\.SIZE (\d+)", data[0] or b"") if data else None
        return int(m.group(1)) if m else None

    def fetch(self, uid: str) -> bytes:
        data = self._call("fetch", self.imap.uid, "FETCH", uid, "(BODY.PEEK[])")
        for part in data:
            if isinstance(part, tuple) and len(part) == 2:
                return bytes(part[1])
        raise CollectorError(f"IMAP fetch of message {uid} returned no body")

    def add_flag(self, uids: list[str], flag: str) -> None:
        if uids:
            self._call(
                "store",
                self.imap.uid,
                "STORE",
                ",".join(uids),
                "+FLAGS.SILENT",
                f"({flag})",
            )

    def logout(self) -> None:
        try:
            self.imap.logout()
        except (OSError, imaplib.IMAP4.error):
            pass


def mailbox_from_env() -> Mailbox:
    return ImapMailbox(ImapSettings())


class IngestSettings(BaseSettings):
    """Ingest settings other than the mailbox (BK_INGEST_*)."""

    model_config = SettingsConfigDict(
        env_prefix="BK_INGEST_", env_file=".env", extra="ignore"
    )
    # authserv-id of the receiving mail server's Authentication-Results header.
    authserv_id: str | None = None


def authserv_id_from_env() -> str | None:
    value = (IngestSettings().authserv_id or "").strip()
    return value or None


NO_AUTHSERV_ID = (
    "email_ingest needs BK_INGEST_AUTHSERV_ID (the authserv-id the receiving mail "
    "server writes in Authentication-Results) to check senders; set it, or turn "
    "off require_authenticated for this source"
)


# --- config -------------------------------------------------------------------------


def _imap_safe(v: str, what: str) -> str:
    v = v.strip()
    if not v or len(v) > 200 or not _IMAP_SAFE.match(v):
        raise ValueError(f"{what} must be 1-200 characters, no quotes or backslashes")
    return v


class EmailIngestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sender: str = Field(
        description="Sender address, or a pattern with * and ? (for example "
        "*@alerts.example.org)."
    )
    subject_pattern: str | None = Field(
        default=None,
        description="Only emails whose subject matches this pattern (* and ?; "
        "case-insensitive).",
    )
    parse_mode: Literal["links", "message"] = Field(
        default="links",
        description="links: each link in the email is an item. message: one item "
        "per email (its subject, and its first matching link).",
    )
    link_pattern: str | None = Field(
        default=None,
        description="Only links matching this pattern (* and ?), for example "
        "https://board.example/tender/*.",
    )
    min_title_chars: Annotated[int, Field(ge=1, le=100)] = Field(
        default=12, description="links mode: skip links whose text is shorter."
    )
    folder: str = Field(default="INBOX", description="Mailbox folder to read.")
    since_days: Annotated[int, Field(ge=1, le=90)] = Field(
        default=14, description="Only look at emails received in the last N days."
    )
    max_messages: Annotated[int, Field(ge=1, le=200)] = Field(
        default=50, description="Read at most this many new emails per run."
    )
    require_authenticated: bool = Field(
        default=True,
        description="Only trust emails the receiving server marked dmarc=pass or "
        "dkim=pass for the sender's domain (guards against forged senders). The "
        "server is identified by BK_INGEST_AUTHSERV_ID; without it the source "
        "does not run.",
    )

    @field_validator("sender")
    @classmethod
    def _sender(cls, v: str) -> str:
        v = _imap_safe(v, "sender").lower()
        if "@" not in v or " " in v:
            raise ValueError("sender must be an address or address pattern")
        return v

    @field_validator("subject_pattern", "link_pattern")
    @classmethod
    def _pattern(cls, v: str | None) -> str | None:
        return v if v is None else _imap_safe(v, "pattern")

    @field_validator("folder")
    @classmethod
    def _folder(cls, v: str) -> str:
        return _imap_safe(v, "folder")


def parse_config(config: dict[str, Any]) -> EmailIngestConfig:
    return parse_model(EmailIngestConfig, config, "email_ingest")


# --- message parsing --------------------------------------------------------------------


def _domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].lower().strip(".")


def _authserv_id(header: str) -> str:
    """The authserv-id of one Authentication-Results value (RFC 8601): the first
    token before the first ';', comments removed, optional version dropped."""
    head = re.sub(r"\([^)]*\)", " ", header.split(";", 1)[0])
    parts = head.split()
    return parts[0].lower().strip(".") if parts else ""


def authenticated(msg: EmailMessage, from_addr: str, authserv_id: str) -> bool:
    """dmarc=pass for the From domain, or dkim=pass with header.d covering it,
    in the topmost Authentication-Results header written by ``authserv_id`` (the
    receiving server). Headers from any other authserv-id, and any lower header
    with the same id, are ignored: the sender can write those."""
    wanted = authserv_id.strip().lower().strip(".")
    if not wanted:
        return False
    ours = [
        str(h)
        for h in msg.get_all("Authentication-Results") or []
        if _authserv_id(str(h)) == wanted
    ]
    if not ours:
        return False
    top = ours[0].lower()
    domain = _domain(from_addr)
    for clause in re.split(r";", top)[1:]:
        clause = clause.strip()
        if clause.startswith("dmarc=pass"):
            m = re.search(r"header\.from=([a-z0-9.-]+)", clause)
            if m and m.group(1).strip(".") == domain:
                return True
        if clause.startswith("dkim=pass"):
            m = re.search(r"header\.d=([a-z0-9.-]+)", clause)
            if m:
                d = m.group(1).strip(".")
                if domain == d or domain.endswith("." + d):
                    return True
    return False


def _bodies(msg: EmailMessage) -> tuple[str | None, str | None]:
    html = plain = None
    for part in msg.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        ctype = part.get_content_type()
        if ctype not in ("text/html", "text/plain"):
            continue
        try:
            content = part.get_content()
        except (LookupError, ValueError):
            payload = part.get_payload(decode=True) or b""
            content = payload.decode("utf-8", errors="replace")
        if not isinstance(content, str):
            continue
        if ctype == "text/html" and html is None:
            html = content
        elif ctype == "text/plain" and plain is None:
            plain = content
    return html, plain


def _match(pattern: str | None, value: str) -> bool:
    return pattern is None or fnmatch.fnmatchcase(value.lower(), pattern.lower())


_BLOCK_TAGS = ("p", "li", "td", "div", "tr", "section", "article")


def _context(a: LexborNode) -> str | None:
    node = a.parent
    while node is not None and node.tag not in _BLOCK_TAGS:
        node = node.parent
    return clean(node.text(separator=" "), 500) if node is not None else None


def html_links(html: str) -> list[tuple[str, str, str | None]]:
    """(href, anchor text, surrounding block text) for each link, in order."""
    tree = LexborHTMLParser(html)
    out = []
    for a in tree.css("a[href]")[: MAX_LINKS_PER_MESSAGE * 5]:
        out.append(
            (
                a.attributes.get("href") or "",
                clean(a.text(separator=" "), 500) or "",
                _context(a),
            )
        )
    return out


def text_links(text: str) -> list[tuple[str, str, str | None]]:
    """Links in a plain-text body. The title is the line's text without the URL,
    else the nearest non-empty line above it."""
    out = []
    previous = ""
    for line in text.splitlines():
        urls = _TEXT_URL.findall(line)
        rest = clean(_TEXT_URL.sub(" ", line), 500) or ""
        rest = rest.strip(" :-–|<>")
        for url in urls:
            out.append((url.rstrip(".,;"), rest or previous, clean(line, 500)))
        if not urls and line.strip():
            previous = clean(line, 500) or ""
    return out[: MAX_LINKS_PER_MESSAGE * 5]


def message_items(
    raw: bytes,
    cfg: EmailIngestConfig,
    source_id,
    fetched_at: datetime,
    authserv_id: str | None = None,
) -> list[RawItem] | None:
    """Items from one email, or None when the email is not this source's (sender,
    subject or authentication do not match)."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    assert isinstance(msg, EmailMessage)
    from_addr = parseaddr(str(msg.get("From", "")))[1].lower()
    subject = clean(str(msg.get("Subject", "")), 500) or ""
    if not from_addr or not _match(cfg.sender, from_addr):
        return None
    if not _match(cfg.subject_pattern, subject):
        return None
    if cfg.require_authenticated:
        if not authserv_id:
            raise CollectorError(NO_AUTHSERV_ID)
        if not authenticated(msg, from_addr, authserv_id):
            return None
    html, plain = _bodies(msg)
    links = html_links(html) if html else text_links(plain or "")
    published = rfc822_to_iso(str(msg.get("Date", ""))) or None
    extra = {"email_subject": subject, "email_from": from_addr}
    items: list[RawItem] = []
    seen: set[str] = set()
    for href, text, context in links:
        url = http_link(None, href)
        if url is None or url in seen or not _match(cfg.link_pattern, url):
            continue
        if cfg.parse_mode == "message":
            body = html_text(html) if html else clean(plain, MAX_SNIPPET)
            return [
                RawItem(
                    source_id=source_id,
                    url=url,
                    title=subject or url,
                    fetched_at=fetched_at,
                    listed_published=published,
                    snippet=body,
                    extra=extra,
                )
            ]
        title = html_text(text, 500)
        if not title or len(title) < cfg.min_title_chars:
            continue
        seen.add(url)
        items.append(
            RawItem(
                source_id=source_id,
                url=url,
                title=title,
                fetched_at=fetched_at,
                listed_published=published,
                snippet=context if context and context != title else None,
                extra=extra,
            )
        )
        if len(items) >= MAX_LINKS_PER_MESSAGE:
            break
    return items


# --- collector ------------------------------------------------------------------------


def done_keyword(source_id) -> str:
    return f"BkDone{source_id.hex[:12]}"


def _imap_date(d: datetime) -> str:
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"


def _server_from_filter(sender: str) -> str | None:
    """Longest literal piece of the sender pattern, for the server-side FROM
    search (the exact pattern is applied here afterwards)."""
    pieces = [p for p in re.split(r"[*?\[\]]", sender) if len(p) >= 3]
    return max(pieces, key=len) if pieces else None


class EmailIngestCollector:
    def __init__(
        self,
        mailbox_factory: Callable[[], Mailbox] = mailbox_from_env,
        *,
        preview: bool = False,
        now=utc_now,
        authserv_id: Callable[[], str | None] = authserv_id_from_env,
    ) -> None:
        self.mailbox_factory = mailbox_factory
        self.preview = preview
        self.now = now
        self.authserv_id = authserv_id
        self._authserv: str | None = None
        # (folder, uids, flag, uid validity) read by fetch, flagged by after_commit.
        self._pending: tuple[str, list[str], str, str | None] | None = None

    def fetch(self, source) -> list[RawItem]:
        cfg = parse_config(source.config or {})
        self._authserv = self.authserv_id()
        if cfg.require_authenticated and not self._authserv:
            raise CollectorError(NO_AUTHSERV_ID)  # before opening the mailbox
        box = self.mailbox_factory()
        try:
            return self._collect(box, source, cfg)
        finally:
            box.logout()

    def _collect(self, box: Mailbox, source, cfg: EmailIngestConfig) -> list[RawItem]:
        box.select(cfg.folder, readonly=self.preview)
        flag = done_keyword(source.id) if box.supports_keywords() else "\\Seen"
        since = _imap_date(self.now().astimezone(UTC) - timedelta(days=cfg.since_days))
        criteria = ["SINCE", since]
        criteria += ["UNKEYWORD", flag] if flag != "\\Seen" else ["UNSEEN"]
        if piece := _server_from_filter(cfg.sender):
            criteria += ["FROM", f'"{piece}"']
        uids = box.search(criteria)
        limit = min(cfg.max_messages, 5) if self.preview else cfg.max_messages
        items: list[RawItem] = []
        seen: set[str] = set()
        done: list[str] = []
        fetched_at = self.now()
        for uid in uids[:limit]:
            size = box.size(uid)
            if size is not None and size > MAX_MESSAGE_BYTES:
                continue  # left unflagged; never read
            raw = box.fetch(uid)
            if len(raw) > MAX_MESSAGE_BYTES:
                continue
            found = message_items(raw, cfg, source.id, fetched_at, self._authserv)
            if found is None:
                continue  # not this source's mail: leave it for others
            done.append(uid)
            for item in found:
                if item.url not in seen:
                    seen.add(item.url)
                    items.append(item)
        if done and not self.preview:
            self._pending = (cfg.folder, done, flag, _validity(box))
        return items

    def after_commit(self, source) -> None:
        """Flag the messages the last ``fetch`` read. The runner calls this only
        after it has committed the run's ingest; never on a rollback."""
        pending, self._pending = self._pending, None
        if pending is None or self.preview:
            return
        folder, uids, flag, validity = pending
        box = self.mailbox_factory()
        try:
            box.select(folder, readonly=False)
            now_validity = _validity(box)
            if validity is not None and now_validity != validity:
                log.warning(
                    "source %s: UIDVALIDITY of %s changed (%s -> %s); %d messages "
                    "left unflagged and will be read again",
                    getattr(source, "name", source),
                    folder,
                    validity,
                    now_validity,
                    len(uids),
                )
                return
            box.add_flag(uids, flag)
        finally:
            box.logout()


def _validity(box: Mailbox) -> str | None:
    fn = getattr(box, "uid_validity", None)
    return fn() if callable(fn) else None
