"""Stage 5, extract: text -> structured record, every field with a quoted snippet.

The model's reply is checked here before anything reaches the catalogue:

* a field whose snippet does not occur in the source text (after whitespace, quote
  and dash normalisation) is dropped, as if the model had returned null;
* the summary is cut to two sentences, dropped if it copies the source verbatim
  (spec 10: our own words), and for investment items dropped if it carries
  recommendation language (spec 1 non-goals, spec 10);
* currency codes must be ISO 4217-shaped; amounts must be non-negative numbers
  quoted from a snippet that contains digits.

Dates stay as the model's ISO strings plus snippet; the validate stage parses them
and enforces the explicit-year rule.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field

from blackkite.db.models import STREAMS
from blackkite.llm.client import LLMClient
from blackkite.llm.prompt import load_prompt

PROMPT_VERSION = "extract-v1"
TOOL_NAME = "record_opportunity"
TOOL_DESCRIPTION = (
    "Record the structured fields of one opportunity notice. Every value carries "
    "a snippet copied verbatim from the source text; unknown values are null."
)
MIN_SNIPPET_CHARS = 3
TAG_KINDS = {"sector": "sector", "service_type": "service", "capability": "capability"}
TAG_MAX_LEN = 100

# --- Reply schema (the tool's input_schema) -----------------------------------------


class Quoted(BaseModel):
    value: str | None = Field(default=None, description="The value, or null")
    snippet: str | None = Field(
        default=None, description="Verbatim passage from the source text stating it"
    )


class QuotedNumber(BaseModel):
    value: float | str | None = Field(default=None, description="A plain number")
    snippet: str | None = None


class QuotedItem(BaseModel):
    text: str
    snippet: str | None = None


class QuotedTag(BaseModel):
    tag: str
    kind: str = Field(description="sector | service_type | capability")
    snippet: str | None = None


class ExtractionReply(BaseModel):
    is_opportunity: bool = True
    not_opportunity_reason: str | None = None
    stream: Quoted = Field(default_factory=Quoted)
    subtype: Quoted = Field(default_factory=Quoted)
    title: Quoted = Field(default_factory=Quoted)
    organisation: Quoted = Field(default_factory=Quoted)
    organisation_short: Quoted = Field(default_factory=Quoted)
    summary: Quoted = Field(default_factory=Quoted)
    published_at: Quoted = Field(default_factory=Quoted)
    deadline_at: Quoted = Field(default_factory=Quoted)
    event_start: Quoted = Field(default_factory=Quoted)
    event_end: Quoted = Field(default_factory=Quoted)
    value_amount: QuotedNumber = Field(default_factory=QuotedNumber)
    value_currency: Quoted = Field(default_factory=Quoted)
    value_note: Quoted = Field(default_factory=Quoted)
    location: Quoted = Field(default_factory=Quoted)
    eligibility: Quoted = Field(default_factory=Quoted)
    requirements: list[QuotedItem] = Field(default_factory=list)
    submission_method: Quoted = Field(default_factory=Quoted)
    fees: Quoted = Field(default_factory=Quoted)
    tags: list[QuotedTag] = Field(default_factory=list)


TEXT_FIELDS = (
    "stream",
    "subtype",
    "title",
    "organisation",
    "organisation_short",
    "summary",
    "value_currency",
    "value_note",
    "location",
    "eligibility",
    "submission_method",
    "fees",
)
DATE_FIELDS = ("published_at", "deadline_at", "event_start", "event_end")

# --- Guards --------------------------------------------------------------------------

_QUOTES = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "–": "-",
        "—": "-",
        "−": "-",
        " ": " ",
    }
)
_WS = re.compile(r"\s+")


def normalise_for_match(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    return _WS.sub(" ", text).strip()


def snippet_supported(snippet: str | None, normalised_source: str) -> bool:
    if not snippet:
        return False
    s = normalise_for_match(snippet)
    return len(s) >= MIN_SNIPPET_CHARS and s in normalised_source


# Phrases that turn a factual investment listing into advice. Deliberately phrases,
# not single words: "buy" alone appears in factual text ("minimum to buy").
RECOMMENDATION_PATTERNS = [
    r"\b(?:we|i)\s+(?:strongly\s+)?(?:recommend|advise|suggest)\b",
    r"\brecommend(?:s|ed)?\s+(?:buying|selling|holding|investing|it|this)\b",
    r"\b(?:you|investors|readers)\s+should\b",
    r"\bshould\s+(?:buy|sell|hold|invest|consider)\b",
    r"\b(?:strong\s+)?(?:buy|sell|hold)\s+(?:signal|rating|recommendation|call)\b",
    r"\bstrong\s+buy\b",
    (
        r"\b(?:attractive|lucrative|undervalued|overvalued|excellent|great|good|"
        r"smart|safe|solid|compelling)\s+(?:investment|opportunity|buy|bet|returns?|"
        r"yield|pick|entry\s+point)\b"
    ),
    r"\bworth\s+(?:buying|investing|a\s+look)\b",
    r"\b(?:don'?t|do\s+not)\s+miss\b",
    r"\bconsider\s+(?:buying|investing|adding|selling)\b",
    r"\bguaranteed\s+(?:returns?|profits?|gains?)\b",
    r"\b(?:will|set\s+to|likely\s+to|expected\s+to)\s+(?:outperform|rise|soar|rally)\b",
    r"\bbuy\s+now\b",
    r"\bget\s+in\s+(?:early|now)\b",
]
_RECOMMENDATION_RE = re.compile("|".join(RECOMMENDATION_PATTERNS), re.IGNORECASE)


def recommendation_language(text: str | None) -> str | None:
    """The first advice-like phrase in ``text``, or None."""
    if not text:
        return None
    m = _RECOMMENDATION_RE.search(text)
    return m.group(0) if m else None


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def first_sentences(text: str, n: int = 2) -> str:
    parts = _SENTENCE_END.split(text.strip())
    return " ".join(parts[:n]).strip()


_CURRENCY_ALIASES = {
    "FRW": "RWF",
    "RWF": "RWF",
    "RFW": "RWF",
    "RF": "RWF",
    "US$": "USD",
    "$": "USD",
    "USD": "USD",
    "€": "EUR",
    "EURO": "EUR",
    "EUROS": "EUR",
}


def normalise_currency(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().upper()
    v = _CURRENCY_ALIASES.get(v, v)
    return v if re.fullmatch(r"[A-Z]{3}", v) else None


def parse_amount(value: float | str | None) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            cleaned = re.sub(r"[,\s_]", "", value)
            if not re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
                return None
            amount = Decimal(cleaned)
        else:
            amount = Decimal(str(value))
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0 or amount >= Decimal(10) ** 18:
        return None
    return amount.quantize(Decimal("0.01"))


# --- Result --------------------------------------------------------------------------


@dataclass
class Extracted:
    """A checked reply. ``values`` uses opportunity column names; dates are still the
    model's ISO strings (validate parses them)."""

    is_opportunity: bool = True
    not_opportunity_reason: str | None = None
    values: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)  # unsupported snippets
    reasons: list[str] = field(default_factory=list)  # for needs_review
    model: str | None = None
    prompt_version: str = PROMPT_VERSION


def check_reply(
    reply: ExtractionReply, source_text: str, allowed_streams: list[str]
) -> Extracted:
    src = normalise_for_match(source_text)
    out = Extracted(
        is_opportunity=reply.is_opportunity,
        not_opportunity_reason=reply.not_opportunity_reason,
    )

    def keep(name: str, value: Any, snippet: str | None) -> bool:
        if value is None or (isinstance(value, str) and not value.strip()):
            return False
        if not snippet_supported(snippet, src):
            out.dropped.append(name)
            return False
        out.values[name] = value.strip() if isinstance(value, str) else value
        out.evidence[name] = {"snippet": snippet}
        return True

    for name in TEXT_FIELDS:
        q: Quoted = getattr(reply, name)
        keep(name, q.value, q.snippet)

    # Stream: one of the four, and one this source feeds.
    stream = out.values.get("stream")
    if stream is not None:
        stream = stream.lower()
        if stream not in STREAMS or stream not in allowed_streams:
            out.values.pop("stream")
            out.evidence.pop("stream")
            out.reasons.append(
                f"extracted stream {stream!r} is not one this source feeds"
            )
        else:
            out.values["stream"] = stream

    # Currency.
    if "value_currency" in out.values:
        code = normalise_currency(out.values["value_currency"])
        if code is None:
            out.reasons.append(
                f"currency {out.values['value_currency']!r} is not an ISO code"
            )
            out.values.pop("value_currency")
            out.evidence.pop("value_currency")
        else:
            out.values["value_currency"] = code

    # Amount: supported snippet that contains digits.
    amount = parse_amount(reply.value_amount.value)
    if amount is not None:
        snip = reply.value_amount.snippet
        if snip and re.search(r"\d", snip) and snippet_supported(snip, src):
            out.values["value_amount"] = amount
            out.evidence["value_amount"] = {"snippet": snip}
        else:
            out.dropped.append("value_amount")
    elif reply.value_amount.value is not None:
        out.reasons.append(f"amount {reply.value_amount.value!r} is not a number")

    # Dates: keep the ISO value and the snippet; validate decides. A snippet that
    # does not occur in the text cannot support anything.
    for name in DATE_FIELDS:
        q = getattr(reply, name)
        if q.snippet and snippet_supported(q.snippet, src):
            out.evidence[name] = {"snippet": q.snippet}
            if q.value:
                out.values[name] = q.value.strip()
        elif q.value or q.snippet:
            out.dropped.append(name)

    # Requirements: list of strings, snippets in evidence.
    reqs, req_snips = [], []
    for item in reply.requirements:
        if item.text.strip() and snippet_supported(item.snippet, src):
            reqs.append(item.text.strip())
            req_snips.append(item.snippet)
        else:
            out.dropped.append("requirements[]")
    if reqs:
        out.values["requirements"] = reqs
        out.evidence["requirements"] = {"snippets": req_snips}

    # Tags: "kind:label", lowercase, unique.
    tags: list[str] = []
    tag_snips: dict[str, str] = {}
    for t in reply.tags:
        kind = TAG_KINDS.get(t.kind.strip().lower())
        label = _WS.sub(" ", t.tag.strip().lower())
        if not kind or not label:
            continue
        if not snippet_supported(t.snippet, src):
            out.dropped.append("tags[]")
            continue
        tag = f"{kind}:{label}"[:TAG_MAX_LEN]
        if tag not in tag_snips:
            tags.append(tag)
            tag_snips[tag] = t.snippet or ""
    if tags:
        out.values["tags"] = tags
        out.evidence["tags"] = {"snippets": tag_snips}

    # Summary: our words, two sentences, no advice for investments.
    summary = out.values.get("summary")
    if summary is not None:
        summary = first_sentences(summary, 2)
        norm_summary = normalise_for_match(summary)
        if len(norm_summary) > 40 and norm_summary in src:
            out.values.pop("summary")
            out.evidence.pop("summary")
            out.reasons.append("summary copied the source verbatim; removed")
        else:
            out.values["summary"] = summary
    # Investment guard: whenever the item is, or may be, an investment item.
    stream = out.values.get("stream")
    if "investment" in allowed_streams and stream in ("investment", None):
        strip_advice(out)

    if out.dropped:
        out.reasons.append(
            "dropped fields whose snippet is not in the source text: "
            + ", ".join(sorted(set(out.dropped)))
        )
    return out


def strip_advice(out: Extracted) -> None:
    """Remove summary / value_note that carry recommendation language (spec 1
    non-goals, spec 10). Idempotent; ingest calls it again for any record filed
    under ``investment``."""
    for name in ("summary", "value_note"):
        phrase = recommendation_language(out.values.get(name))
        if phrase:
            out.values.pop(name)
            out.evidence.pop(name, None)
            out.reasons.append(
                f"{name} removed: recommendation language ({phrase!r}) "
                "in an investment item"
            )


def build_user_message(
    source_text: str, *, source_name: str, source_kind: str, streams: list[str]
) -> str:
    return (
        f"Source: {source_name} (kind: {source_kind}; streams: {', '.join(streams)})\n"
        f"<source_text>\n{source_text}\n</source_text>"
    )


def extract(
    llm: LLMClient,
    source_text: str,
    *,
    source_name: str,
    source_kind: str,
    streams: list[str],
) -> Extracted:
    """One model call. Raises LLMError; the caller decides what that means."""
    prompt = load_prompt(PROMPT_VERSION)
    reply = llm.structured(
        system=prompt.text,
        user=build_user_message(
            source_text,
            source_name=source_name,
            source_kind=source_kind,
            streams=streams,
        ),
        schema=ExtractionReply,
        tool_name=TOOL_NAME,
        tool_description=TOOL_DESCRIPTION,
    )
    out = check_reply(reply, source_text, streams)
    out.model = llm.model
    out.prompt_version = prompt.version
    return out


def embedding_text(title: str, summary: str | None, tags: list[str]) -> str:
    parts = [title]
    if summary:
        parts.append(summary)
    if tags:
        parts.append("Tags: " + ", ".join(tags))
    return "\n".join(parts)
