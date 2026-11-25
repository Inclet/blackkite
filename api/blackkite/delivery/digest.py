"""Weekly digest email (spec 8; design/reference/digest-email.html).

`render_digest(view)` is a pure function: a typed DigestView in, (subject, html,
text) out. Choosing and wording the items happens upstream; this module only lays
them out. The HTML follows the owner's email rulings: nested tables with inline
styles only (decision 7), system fonts (Helvetica, Arial), bold at 700 as on the
board (decision 8), the kite as a PNG <img>, full dates, no SVG, no flexbox, no
<style> blocks, no classes, no web fonts.

`render_digest_preview(view)` wraps the same email body in the board's preview
chrome (the "Subject:/From:" lines above the card, design board lines 13-15) for
the visual check. That chrome is never sent.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

Stream = Literal["tender", "investment", "funding", "event"]

# Label text colour and swatch colour per stream (board lines 35, 42, 49; investment
# from design/tokens.css --bk-investment-text / --bk-investment, not on the board).
STREAM_COLOURS: dict[str, tuple[str, str]] = {
    "tender": ("#7A5200", "#F2A83B"),
    "investment": ("#0E5F56", "#1FA898"),
    "funding": ("#8F2F1F", "#F0705A"),
    "event": ("#333F9E", "#6C7BF2"),
}

# A bare "#" is the board's placeholder link. It is accepted only while
# allow_placeholder_links() is active (the reference fixture, for the preview);
# a real digest carries http(s) links only.
PLACEHOLDER_LINK = "#"
_allow_placeholder: ContextVar[bool] = ContextVar(
    "bk_digest_allow_placeholder", default=False
)


@contextmanager
def allow_placeholder_links() -> Iterator[None]:
    """Let DigestItem/DigestView/DigestFooter accept "#" links inside this block."""
    reset = _allow_placeholder.set(True)
    try:
        yield
    finally:
        _allow_placeholder.reset(reset)


def _check_link(value: str) -> str:
    """Absolute http/https URL with a host; rejects javascript:, data:, relative, etc."""
    if value == PLACEHOLDER_LINK and _allow_placeholder.get():
        return value
    if (
        not value
        or value != value.strip()
        or any(ord(c) < 0x21 or ord(c) == 0x7F for c in value)
    ):
        raise ValueError(
            "link must be an http(s) URL without spaces or control characters"
        )
    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise ValueError("link is not a valid URL") from exc
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise ValueError("link must be an absolute http or https URL")
    return value


# Every href in the digest goes through this type.
LinkUrl = Annotated[str, AfterValidator(_check_link)]

CTA_LABEL = "Open your feed"
DEFAULT_LOGO_SRC = "cid:kite-logo"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DigestItem(_Model):
    stream: Stream
    # Profile name shown as "FOR <NAME>"; None when the item is not tied to one profile.
    profile_label: str | None = None
    title: str
    url: LinkUrl
    # One line in our own words: organisation and the reason it matched.
    summary: str
    # The date phrase shown in bold, e.g. "Closes Mon 30 Nov" or "Tue 1 to Wed 2 Dec".
    date_line: str
    # Trust state when not confirmed, e.g. "not yet confirmed at the source".
    trust_note: str | None = None
    # The stated value, e.g. "Value: FRW 12,000,000" (spec 8). Not on the board;
    # the row is left out when None, so the reference render is unchanged.
    value_line: str | None = None

    @property
    def label(self) -> str:
        label = self.stream.upper()
        if self.profile_label:
            label += f" · FOR {self.profile_label.upper()}"
        return label

    @property
    def label_colour(self) -> str:
        return STREAM_COLOURS[self.stream][0]

    @property
    def swatch_colour(self) -> str:
        return STREAM_COLOURS[self.stream][1]


class DigestFooter(_Model):
    source_count: int = Field(ge=0)
    # How often, as a phrase completing "You get this ...", e.g. "every Monday".
    frequency: str
    change_frequency_url: LinkUrl
    unsubscribe_url: LinkUrl

    @property
    def sources_line(self) -> str:
        if self.source_count == 1:
            return "The 1 source was checked this week."
        return f"All {self.source_count} sources were checked this week."


class DigestView(_Model):
    subject: str
    sender: str = "Blackkite"
    first_name: str
    issue_date: date
    greeting: str = "Good morning"
    intro: str
    items: list[DigestItem]
    cta_url: LinkUrl
    more_count: int = Field(ge=0)
    footer: DigestFooter
    # Saved items closing within 7 days (spec 8). Not on the board; the block is
    # left out when empty, so the reference render is unchanged.
    closing_soon: list[DigestItem] = Field(default_factory=list)
    closing_heading: str = "Closing in 7 days"

    @property
    def issue_date_text(self) -> str:
        """Full date, as the design asks: "Monday 23 November 2026"."""
        d = self.issue_date
        return f"{d:%A} {d.day} {d:%B} {d.year}"

    @property
    def heading(self) -> str:
        return f"{self.greeting}, {self.first_name}"

    @property
    def more_line(self) -> str | None:
        if self.more_count == 0:
            return None
        verb = "is" if self.more_count == 1 else "are"
        return f"{self.more_count} more {verb} waiting there."


@lru_cache
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(Path(__file__).resolve().parent / "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def _html(view: DigestView, logo_src: str, preview: bool) -> str:
    return (
        _env()
        .get_template("digest.html.j2")
        .render(v=view, logo_src=logo_src, preview=preview, cta_label=CTA_LABEL)
    )


def _text_items(items: list[DigestItem]) -> list[str]:
    lines: list[str] = []
    for item in items:
        date_line = item.date_line + (
            f" · {item.trust_note}" if item.trust_note else ""
        )
        lines += [item.label, item.title, item.summary]
        if item.value_line:
            lines.append(item.value_line)
        lines += [date_line, item.url, ""]
    return lines


def _text(view: DigestView) -> str:
    lines = [view.heading, "", view.intro, ""]
    lines += _text_items(view.items)
    if view.closing_soon:
        lines += [view.closing_heading.upper(), ""]
        lines += _text_items(view.closing_soon)
    lines.append(f"{CTA_LABEL}: {view.cta_url}")
    if view.more_line:
        lines.append(view.more_line)
    f = view.footer
    lines += [
        "",
        "--",
        f"{f.sources_line} Dates are shown in full because you may read this later.",
        f"You get this {f.frequency}.",
        f"Change how often: {f.change_frequency_url}",
        f"Stop these emails: {f.unsubscribe_url}",
        "",
    ]
    return "\n".join(lines)


def render_digest(
    view: DigestView, logo_src: str = DEFAULT_LOGO_SRC
) -> tuple[str, str, str]:
    """Return (subject, html, text) for one weekly digest email.

    logo_src: where the <img> finds the kite PNG (blackkite.delivery.logo.kite_png()).
    Default is a cid: reference for an inline MIME part with Content-ID <kite-logo>.
    """
    return view.subject, _html(view, logo_src, preview=False), _text(view)


def render_digest_preview(view: DigestView, logo_src: str = "kite.png") -> str:
    """The email body inside the board's preview chrome, as one HTML page."""
    return _html(view, logo_src, preview=True)
