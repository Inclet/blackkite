"""Text views of an opportunity and a profile, shared by rules, match and the model.

``notice_text`` is what the scoring model reads and the only text a quote may come
from: the notice's own words (title, organisation, extracted fields, every
supporting snippet, document text). Our summary is not in it, so a reason can never
"quote" words we wrote.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from blackkite.db.models import Opportunity, Profile
from blackkite.pipeline.extract import normalise_for_match

_NOTICE_FIELDS = (
    "eligibility",
    "submission_method",
    "fees",
    "location",
    "value_note",
)


def _snippets(evidence: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key, entry in (evidence or {}).items():
        if key.startswith("_") or not isinstance(entry, dict):
            continue
        if isinstance(entry.get("snippet"), str):
            out.append(entry["snippet"])
        snips = entry.get("snippets")
        if isinstance(snips, list):
            out.extend(s for s in snips if isinstance(s, str))
        elif isinstance(snips, dict):
            out.extend(s for s in snips.values() if isinstance(s, str))
    return out


def notice_parts(opp: Opportunity, documents: Iterable[str]) -> list[str]:
    parts = [opp.title]
    if opp.organisation:
        parts.append(opp.organisation)
    for name in _NOTICE_FIELDS:
        value = getattr(opp, name)
        if value:
            parts.append(str(value))
    for req in opp.requirements or []:
        if isinstance(req, str) and req.strip():
            parts.append(req)
    seen = set(parts)
    for s in _snippets(opp.evidence):
        if s not in seen:
            parts.append(s)
            seen.add(s)
    parts.extend(d for d in documents if d and d.strip())
    return parts


def notice_text(
    opp: Opportunity, documents: Iterable[str], max_chars: int | None = None
) -> str:
    text = "\n".join(notice_parts(opp, documents))
    return text[:max_chars] if max_chars else text


def clean_quote(quote: str) -> str:
    """Normalised quote without surrounding whitespace, a final full stop, or a
    pair of quotation marks wrapped around the whole of it."""
    q = normalise_for_match(quote).strip().rstrip(".").strip()
    if len(q) >= 2 and q[0] == q[-1] and q[0] in "\"'":
        q = q[1:-1].strip()
    return q


def quote_supported(
    quote: str | None, normalised_text: str, min_chars: int = 8
) -> bool:
    if not quote:
        return False
    q = clean_quote(quote)
    return len(q) >= min_chars and q.lower() in normalised_text.lower()


# --- tokens for tag overlap ------------------------------------------------------------

STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "or",
        "of",
        "for",
        "the",
        "to",
        "in",
        "on",
        "at",
        "by",
        "with",
        "from",
        "as",
        "is",
        "are",
        "be",
        "this",
        "that",
        "these",
        "those",
        "its",
        "it",
        "into",
        "via",
        "per",
        "any",
        "all",
        "other",
        "others",
        "general",
        "various",
        "services",
        "service",
        "provision",
        "supply",
        "supplies",
        "including",
        "include",
        "etc",
    ]
)
_TOKEN = re.compile(r"[a-z0-9]+")

# Small domain expansions so cheap matching sees that "dry freight" is transport.
# Keys and values are single tokens (after lowercasing).
EXPANSIONS: dict[str, tuple[str, ...]] = {
    "freight": (
        "transport",
        "transportation",
        "haulage",
        "trucking",
        "logistics",
        "cargo",
    ),
    "cold": ("refrigerated", "reefer", "frozen", "chilled", "perishable"),
    "chain": ("refrigerated", "reefer", "logistics"),
    "distribution": ("delivery", "deliveries", "logistics", "transport"),
    "last": ("delivery",),
    "software": ("ict", "system", "systems", "application", "platform", "digital"),
    "development": ("developer", "developers"),
    "ai": ("artificial", "intelligence", "machine", "learning", "ml"),
    "ml": ("machine", "learning", "ai"),
    "data": ("analytics", "database", "statistics", "dataset"),
    "digital": ("ict", "technology", "digitalisation", "digitization", "digitisation"),
    "consulting": ("consultancy", "consultant", "consultants", "advisory"),
    "tech": ("technology", "ict", "digital"),
    "fintech": ("finance", "financial", "payments", "banking"),
    "agriculture": ("agri", "agribusiness", "farming", "farmers", "agricultural"),
    "food": ("agrifood", "nutrition"),
    "startups": ("startup", "entrepreneurs", "founders", "venture"),
    "investors": ("investor", "investment", "venture"),
    "networking": ("meetup", "mixer", "networking"),
    "bonds": ("bond", "treasury"),
    "bills": ("bill", "treasury"),
    "shares": ("share", "equity", "ipo", "listing"),
    "land": ("plot", "plots", "property"),
    "estate": ("property", "housing", "reit"),
}


def tokens(text: str) -> set[str]:
    return {
        t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS and len(t) > 1
    }


def _stem(t: str) -> str:
    return t[:6] if len(t) > 6 else t


def term_tokens(term: str) -> set[str]:
    """A profile term's tokens plus their expansions, stemmed."""
    base = tokens(term)
    out = set(base)
    for t in base:
        out.update(EXPANSIONS.get(t, ()))
    return {_stem(t) for t in out}


def matched_terms(terms: Iterable[str], opp_tokens: set[str]) -> list[str]:
    """Profile terms that share a (stemmed, expanded) token with the item."""
    stems = {_stem(t) for t in opp_tokens}
    return [t for t in terms if term_tokens(t) & stems]


def opportunity_match_text(opp: Opportunity) -> str:
    tags = [t.split(":", 1)[-1] for t in (opp.tags or [])]
    return " ".join([opp.title, opp.subtype or "", opp.summary or "", *tags])


# --- profile ------------------------------------------------------------------------

PROFILE_TERM_FIELDS = ("services", "sectors", "instruments", "event_topics")


def _str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str) and v.strip()]
    return []


def profile_terms(profile: Profile) -> list[str]:
    data = profile.data or {}
    out: list[str] = []
    for f in PROFILE_TERM_FIELDS:
        out.extend(_str_list(data.get(f)))
    return out


def profile_text(profile: Profile) -> str:
    """What the profile embedding is computed from: its interests, not its owner."""
    data = profile.data or {}
    lines = [f"{profile.name} ({profile.type})"]
    for f in PROFILE_TERM_FIELDS:
        vals = _str_list(data.get(f))
        if vals:
            lines.append(f"{f.replace('_', ' ')}: {', '.join(vals)}")
    if isinstance(data.get("location"), str):
        lines.append(f"location: {data['location']}")
    return "\n".join(lines)
