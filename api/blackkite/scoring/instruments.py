"""Investment instrument kinds: what a personal profile's chosen instruments
mean, and which kind an investment item is (M5 fix list 1). Rules only.

A profile's instruments are free text ("treasury bonds and bills", "RSE
shares"); each is read as phrases naming one or more kinds, never as loose
tokens, so "treasury bonds and bills" is the treasury kind only and does not
take in corporate bonds. A bare "bonds" names both bond kinds.

An item's kind comes from its subtype first, then its tags, then its title
(and, for a bond that names neither kind, its issuer: a government, ministry or
central bank issues treasury bonds; anyone else a corporate bond). An item no
rule recognises has no kind (``None``): missing data never filters.

Kinds:

* ``treasury``: treasury bonds and bills, government securities
* ``corporate_bond``: corporate bonds, commercial paper
* ``equity``: listed shares (RSE), IPOs, rights issues
* ``fund``: unit trusts, collective investment schemes
* ``real_estate``: real estate, land, property
* ``private_deal``: private deals, startups, private placements
"""

from __future__ import annotations

import re
from typing import Any

KINDS = (
    "treasury",
    "corporate_bond",
    "equity",
    "fund",
    "real_estate",
    "private_deal",
)

# Read in this order: the first kind that matches an item's text wins, so
# "corporate bond" is checked before a bare "bond", and every bond word before
# equity (``_first_kind``): an RSE bond listing is a bond.
_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "corporate_bond",
        (r"\bcorporate (?:bonds?|notes?|debt)\b", r"\bcommercial papers?\b"),
    ),
    (
        "treasury",
        (
            r"\btreasur(?:y|ies)\b",
            r"\bt[- ]?bills?\b",
            r"\bt[- ]?bonds?\b",
            r"\bgovernment (?:bonds?|securities|paper)\b",
            r"\bsovereign\b",
            r"\binfrastructure bonds?\b",
        ),
    ),
    (
        "equity",
        (
            r"\bshares?\b",
            r"\bequit(?:y|ies)\b",
            r"\bstocks?\b(?! exchanges?\b)",  # "stock exchange" alone: no kind
            r"\bipos?\b",
            r"\binitial public offer(?:ing)?\b",
            r"\brights issues?\b",
            r"\blisted compan",
            r"\bcross[- ]listing\b",
        ),
    ),
    (
        "fund",
        (
            r"\bunit trusts?\b",
            r"\bcollective investment\b",
            r"\bmutual funds?\b",
            r"\bmoney market funds?\b",
            r"\betfs?\b",
            r"\bexchange[- ]traded funds?\b",
        ),
    ),
    (
        "real_estate",
        (
            r"\breal estate\b",
            r"\bland\b",
            r"\bpropert(?:y|ies)\b",
            r"\bplots?\b",
            r"\breits?\b",
            r"\bhousing\b",
        ),
    ),
    (
        "private_deal",
        (
            r"\bprivate (?:deals?|placements?|equity|investments?)\b",
            r"\bstart-?ups?\b",
            r"\bangel\b",
            r"\bventure\b",
            r"\bcrowdfund",
        ),
    ),
)
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (k, re.compile("|".join(words), re.IGNORECASE)) for k, words in _WORDS
)
_BOND = re.compile(r"\bbonds?\b", re.IGNORECASE)
_GOVERNMENT = re.compile(
    r"\b(?:government|ministry|minecofin|central bank|national bank|bnr|"
    r"republic of rwanda|treasury)\b",
    re.IGNORECASE,
)


def text_kinds(text: str) -> set[str]:
    """Every kind ``text`` names (a profile instrument may name several)."""
    out = {k for k, p in _PATTERNS if p.search(text)}
    if _BOND.search(text) and not out & {"treasury", "corporate_bond"}:
        out |= {"treasury", "corporate_bond"}  # "bonds": both bond kinds
    return out


def chosen_kinds(profile_data: dict[str, Any] | None) -> set[str] | None:
    """Kinds the profile's instruments name; None when it lists no instruments
    (or none that name a kind), so nothing is judged on them."""
    raw = (profile_data or {}).get("instruments")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return None
    out: set[str] = set()
    for v in raw:
        if isinstance(v, str):
            out |= text_kinds(v)
    return out or None


_BOND_KINDS = ("corporate_bond", "treasury")


def _bond_kind(issuer: str) -> str:
    """The kind of a bond that names neither kind, from its issuer."""
    return "treasury" if _GOVERNMENT.search(issuer) else "corporate_bond"


def _first_kind(text: str | None, issuer: str) -> str | None:
    """The first kind ``text`` names; bond words before any other kind, so a
    "Rwanda Stock Exchange listing of ... bond" is a bond."""
    if not text:
        return None
    for k, p in _PATTERNS:
        if k in _BOND_KINDS and p.search(text):
            return k
    if _BOND.search(text):
        return _bond_kind(issuer)
    for k, p in _PATTERNS:
        if k not in _BOND_KINDS and p.search(text):
            return k
    return None


def item_kind(opp: Any) -> str | None:
    """The investment item's kind, or None when no rule says."""
    if getattr(opp, "stream", None) != "investment":
        return None
    tags = [t.split(":", 1)[-1] for t in (getattr(opp, "tags", None) or [])]
    issuer = f"{opp.organisation or ''} {opp.organisation_short or ''}"
    for text in (getattr(opp, "subtype", None), " | ".join(tags), opp.title):
        kind = _first_kind(text, issuer)
        if kind:
            return kind
    return None


def instrument_chosen(opp: Any, profile_data: dict[str, Any] | None) -> bool | None:
    """True / False when both the item's kind and the profile's instruments are
    known; None when either is not (no judgement)."""
    kinds = chosen_kinds(profile_data)
    kind = item_kind(opp)
    if kinds is None or kind is None:
        return None
    return kind in kinds


# How a kind reads in a reason ("... do not include corporate bonds").
LABELS = {
    "treasury": "treasury bonds and bills",
    "corporate_bond": "corporate bonds",
    "equity": "listed shares",
    "fund": "investment funds",
    "real_estate": "real estate",
    "private_deal": "private deals",
}
