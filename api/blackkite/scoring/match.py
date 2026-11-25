"""Stage 7, match: a cheap shortlist per profile, no model call (spec 5).

Shortlist rule, for a pair that passed the hard filters:

1. An exclusion hit (``profile.data.exclusions``: ``organisations``, ``sectors``,
   ``keywords``) is never shortlisted.
2. **Tag overlap**: profile terms (``services``, ``sectors``, ``instruments``,
   ``event_topics``) are tokenised, expanded with a small domain synonym list
   (``text.EXPANSIONS``) and stemmed; a term hits when it shares a token with the
   item's tags, title, subtype or summary. ``tag_min_overlap`` (default 1) hits
   shortlist the pair.
3. **Embedding similarity**: cosine similarity between the item's embedding and the
   profile embedding, computed by pgvector in the candidate query.
   ``embedding_min_similarity`` (default 0.45) or more shortlists the pair.
4. An item with neither tags nor an embedding (extraction or embedding skipped) is
   shortlisted: there is nothing cheap to judge it on, and missing data must not
   drop it.

Only tender and funding pairs on the shortlist go to the model. Event and
investment pairs never do (spec 7.1: every topic is selected, so they rank on time,
verification and source kind); their match strength only nudges the fit component.

The profile embedding is computed from ``text.profile_text`` through the Embedder
and cached in process, keyed on (profile id, profile version, embedding model). The
cache is lost when the process exits: one embedding call per profile per process.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from blackkite.db.models import Opportunity, Profile
from blackkite.llm.embeddings import Embedder, EmbeddingError
from blackkite.scoring.settings import ScoringSettings
from blackkite.scoring.text import (
    _str_list,
    matched_terms,
    opportunity_match_text,
    profile_terms,
    profile_text,
    tokens,
)

log = logging.getLogger("blackkite.scoring")

_CACHE: dict[tuple[uuid.UUID, int, str], list[float]] = {}
_CACHE_MAX = 1024


def profile_embedding(
    profile: Profile, embedder: Embedder | None
) -> list[float] | None:
    if embedder is None:
        return None
    key = (profile.id, profile.version, embedder.model)
    if key in _CACHE:
        return _CACHE[key]
    try:
        [vector] = embedder.embed([profile_text(profile)])
    except (EmbeddingError, ValueError) as exc:
        log.warning("profile embedding failed for %s: %s", profile.id, exc)
        return None
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = vector
    return vector


def clear_profile_embedding_cache() -> None:
    _CACHE.clear()


@dataclass
class Match:
    shortlisted: bool
    matched: list[str] = field(default_factory=list)
    similarity: float | None = None
    excluded: str | None = None

    @property
    def strength(self) -> float:
        """0..1 rule estimate of fit, for scores made without the model."""
        if self.excluded:
            return 0.0
        s = 0.25 + 0.12 * min(len(self.matched), 3)
        if self.similarity is not None:
            s = max(s, min(1.0, self.similarity))
        return min(s, 0.65)


def _exclusion(opp: Opportunity, profile: Profile, opp_tokens: set[str]) -> str | None:
    ex = (profile.data or {}).get("exclusions")
    if not isinstance(ex, dict):
        return None
    org = f"{opp.organisation or ''} {opp.organisation_short or ''}".lower()
    for name in _str_list(ex.get("organisations")):
        if name.lower() in org:
            return name
    text = opportunity_match_text(opp).lower()
    for word in _str_list(ex.get("keywords")):
        if word.lower() in text:
            return word
    sectors = {t.split(":", 1)[-1] for t in (opp.tags or []) if t.startswith("sector:")}
    for sector in _str_list(ex.get("sectors")):
        if sector.lower() in sectors:
            return sector
    return None


def match(
    opp: Opportunity,
    profile: Profile,
    similarity: float | None,
    settings: ScoringSettings,
) -> Match:
    opp_tokens = tokens(opportunity_match_text(opp))
    excluded = _exclusion(opp, profile, opp_tokens)
    if excluded:
        return Match(False, excluded=excluded, similarity=similarity)
    hits = matched_terms(profile_terms(profile), opp_tokens)
    shortlisted = (
        len(hits) >= settings.tag_min_overlap
        or (similarity is not None and similarity >= settings.embedding_min_similarity)
        or (not opp.tags and opp.embedding is None)
    )
    return Match(shortlisted, hits, similarity)
