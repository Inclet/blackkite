"""Text views of an opportunity and a profile, shared by rules, match and the model.

``notice_text`` is what the scoring model reads and the only text a quote may come
from: the notice's own words (title, organisation, extracted fields, every
supporting snippet, document text). Our summary is not in it, so a reason can never
"quote" words we wrote.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
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


# A light suffix stripper, so "transport" and "transportation", "hospital" and
# "hospitals" meet while "district" and "distribution" do not. At most two
# suffixes, never leaving fewer than four letters.
_SUFFIXES = tuple(
    sorted(
        (
            "isations",
            "izations",
            "isation",
            "ization",
            "ations",
            "ation",
            "ments",
            "ment",
            "ancies",
            "ancy",
            "ency",
            "ings",
            "ing",
            "ants",
            "ant",
            "ators",
            "ator",
            "ated",
            "ates",
            "ate",
            "ers",
            "er",
            "ors",
            "or",
            "ural",
            "ure",
            "ions",
            "ion",
            "ive",
            "ly",
            "ed",
            "al",
            "s",
        ),
        key=len,
        reverse=True,
    )
)


def _strip_once(t: str) -> str:
    if t.endswith("ies") and len(t) > 5:
        return t[:-3] + "y"
    for suf in _SUFFIXES:
        if t.endswith(suf) and len(t) - len(suf) >= 4:
            return t[: -len(suf)]
    return t


def _stem(t: str) -> str:
    return _strip_once(_strip_once(t))


# Words of a multi-word term that say nothing on their own: "dry" in "dry
# season", "chain" in "supply chain", "community" in "community meeting". They
# count inside the whole phrase, never as a hit by themselves (their expansions
# still do: "refrigerated" for "cold").
WEAK_ALONE = frozenset(
    [
        "dry",
        "cold",
        "chain",
        "last",
        "mile",
        "first",
        "community",
        "development",
        "public",
        "local",
        "national",
        "international",
        "small",
        "management",
    ]
)


# A phrase never spans these (separate tags, sentences, list items).
_BREAK = re.compile(r"[\n.;:|,()\[\]]")


def _word_list(text: str) -> list[tuple[str, int, int]]:
    """(token, start, end) for the non-stopword tokens of ``text``, in order."""
    return [
        (m.group(0), m.start(), m.end())
        for m in _TOKEN.finditer(text.lower())
        if m.group(0) not in STOPWORDS and len(m.group(0)) > 1
    ]


def _ordered_tokens(term: str) -> list[str]:
    return [t for t, _, _ in _word_list(term)]


def _alts(token: str) -> set[str]:
    """Stems an item word may have to stand for this term word."""
    return {_stem(token), *(_stem(e) for e in EXPANSIONS.get(token, ()))}


def _surface(text: str, start: int, end: int) -> str:
    """The item's own words, lowercased unless written as an acronym (ICT)."""
    s = " ".join(text[start:end].split())
    words = s.split()
    if words and all(w.isupper() and len(w) > 1 for w in words if w.isalpha()):
        return s
    return s.lower()


@dataclass(frozen=True)
class TermHit:
    """One profile term found in an item's text.

    ``phrase``: the whole term is there, word for word or through the synonym
    list ("refrigerated logistics" for "cold chain"); only then may a reason
    claim the term. Otherwise ``quotes`` are the item words that match a word
    of the term (never a ``WEAK_ALONE`` word by itself)."""

    term: str
    phrase: bool
    literal: bool  # the whole term word for word (no synonym)
    quotes: tuple[str, ...]
    stems: frozenset[str]


def term_hits(terms: Iterable[str], text: str) -> list[TermHit]:
    """Profile terms that occur in ``text`` (see ``TermHit``), in term order."""
    words = _word_list(text)
    stems = [_stem(w) for w, _, _ in words]
    out: list[TermHit] = []
    for term in terms:
        seq = _ordered_tokens(term)
        if not seq:
            continue
        alts = [_alts(t) for t in seq]
        best: TermHit | None = None
        n = len(seq)
        for i in range(len(words) - n + 1):
            if all(stems[i + k] in alts[k] for k in range(n)) and not any(
                _BREAK.search(text[words[i + k][2] : words[i + k + 1][1]])
                for k in range(n - 1)
            ):
                literal = all(stems[i + k] == _stem(seq[k]) for k in range(n))
                hit = TermHit(
                    term,
                    True,
                    literal,
                    (_surface(text, words[i][1], words[i + n - 1][2]),),
                    frozenset(stems[i : i + n]),
                )
                if best is None or (literal and not best.literal):
                    best = hit
                if literal:
                    break
        if best is not None:
            out.append(best)
            continue
        quotes: list[str] = []
        hit_stems: set[str] = set()
        for k, tok in enumerate(seq):
            if n > 1 and tok in WEAK_ALONE:
                allowed = alts[k] - {_stem(tok)}
            else:
                allowed = alts[k]
            for j, (_, a, b) in enumerate(words):
                if stems[j] in allowed and stems[j] not in hit_stems:
                    hit_stems.add(stems[j])
                    quotes.append(_surface(text, a, b))
        if quotes:
            out.append(TermHit(term, False, False, tuple(quotes), frozenset(hit_stems)))
    return out


def mentioned(hits: Iterable[TermHit]) -> list[str]:
    """What a reason may say the item mentions: the item's own words, whole
    phrases first, each once (case-insensitive), and no word already inside a
    phrase listed ("community health", not "community health, health")."""
    hits = list(hits)
    ordered = [q for h in hits if h.phrase for q in h.quotes] + [
        q for h in hits if not h.phrase for q in h.quotes
    ]
    out: list[str] = []
    for q in ordered:
        key = q.lower()
        if any(
            key == o.lower() or re.search(rf"\b{re.escape(key)}\b", o.lower())
            for o in out
        ):
            continue
        out.append(q)
    return out


def opportunity_match_text(opp: Opportunity) -> str:
    tags = [t.split(":", 1)[-1] for t in (opp.tags or [])]
    return "\n".join([opp.title, opp.subtype or "", opp.summary or "", *tags])


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
