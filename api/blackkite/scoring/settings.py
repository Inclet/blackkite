"""Scoring settings (prefix BK_SCORE_). The model name is BK_MODEL_SCORE in
``blackkite.config.Settings``; the key is ANTHROPIC_API_KEY.

Dict and list values are read from the environment as JSON, for example
``BK_SCORE_WEIGHTS='{"fit": 40, "eligibility": 20, "value": 15, "time": 15, "source": 10}'``.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

COMPONENTS = ("fit", "eligibility", "value", "time", "source")


class FitWordRule(BaseModel):
    """docs/api-contract.md section 1 (revised 2026-11-25, owner to confirm).
    Checked in order: strong, good, possible; otherwise null. Flags do not
    change the word: a strong item may carry a "To check" note (WFP board)."""

    strong_fit: float = 0.7
    strong_eligibility: float = 0.7
    good_fit: float = 0.6
    good_eligibility: float = 0.5
    possible_fit: float = 0.4


class TimeRule(BaseModel):
    """Days of preparation time: under ``min_days`` scores ``too_late``; from
    ``min_days`` to ``ideal_days`` rises linearly from ``floor`` to 1.0."""

    min_days: float
    ideal_days: float
    too_late: float = 0.1
    floor: float = 0.3


def _default_time_rules() -> dict[str, TimeRule]:
    return {
        # Tenders and funding need documents, registrations, partners.
        "tender": TimeRule(min_days=3, ideal_days=21),
        "funding": TimeRule(min_days=3, ideal_days=21),
        # Counted from event_start (decision 23 counts event urgency from the start).
        "event": TimeRule(min_days=2, ideal_days=14),
        "investment": TimeRule(min_days=2, ideal_days=10),
    }


class ScoringSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BK_SCORE_", env_file=".env", extra="ignore"
    )

    # Component maxima (spec 7). They sum to 100.
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "fit": 40,
            "eligibility": 20,
            "value": 15,
            "time": 15,
            "source": 10,
        }
    )
    fit_word: FitWordRule = Field(default_factory=FitWordRule)

    # --- Match (stage 7): see blackkite/scoring/match.py -------------------------
    # Cosine similarity (opportunity embedding vs profile embedding) that alone
    # puts a pair on the shortlist.
    embedding_min_similarity: float = Field(default=0.45, ge=-1, le=1)
    # Profile terms (services, sectors, ...) that must hit the item's tags/title
    # for tag overlap alone to shortlist it.
    tag_min_overlap: int = Field(default=1, ge=1)

    # --- Score (stage 8) ----------------------------------------------------------
    # Model calls allowed in one run (score_new_opportunities, backfill_profile,
    # score_user). Pairs past the cap get a rules-only row and are retried next run.
    max_llm_calls_per_run: int = Field(default=200, ge=0)
    # Characters of notice text (fields, snippets, document text) sent per call.
    text_max_chars: int = Field(default=12_000, ge=1_000)
    # Eligibility confidence lost per rule flag on a rules-only score (missing
    # profile data lowers eligibility confidence, spec 7).
    flag_eligibility_penalty: float = Field(default=0.1, ge=0, le=1)
    # Unflagged eligibility confidence of a rules-only score.
    rules_eligibility: float = Field(default=0.5, ge=0, le=1)

    # Investments (spec 7.1 ranks them on time, verification and source): the
    # fit of an item whose instrument kind the profile chose, and of one whose
    # kind it did not (scoring/instruments.py). The gap (x the fit weight) is
    # larger than the time and source weights together, so an unchosen kind
    # always ranks below a chosen one. Unknown kind or no instruments: 0.4.
    instrument_chosen_fit: float = Field(default=0.8, ge=0, le=1)
    instrument_other_fit: float = Field(default=0.1, ge=0, le=1)

    time_rules: dict[str, TimeRule] = Field(default_factory=_default_time_rules)
    # Time score when the deadline (or event start) is unknown.
    time_unknown: float = Field(default=0.4, ge=0, le=1)

    # Source component: verification share, the rest is the best carrying kind.
    verification_share: float = Field(default=0.6, ge=0, le=1)
    verification_scores: dict[str, float] = Field(
        default_factory=lambda: {
            "verified_original": 1.0,
            "unverified": 0.6,
            "aggregator_only": 0.3,
        }
    )
    # "Sources disagree" (evidence._trust == conflict) replaces the above.
    conflict_score: float = Field(default=0.4, ge=0, le=1)
    kind_scores: dict[str, float] = Field(
        default_factory=lambda: {
            "original": 1.0,
            "publisher": 0.8,
            "news": 0.6,
            "community": 0.5,
            "aggregator": 0.3,
        }
    )
    # Private manual items (no source): the user's own entry.
    private_item_kind_score: float = Field(default=0.5, ge=0, le=1)

    @field_validator("weights")
    @classmethod
    def _all_components(cls, v: dict[str, float]) -> dict[str, float]:
        missing = set(COMPONENTS) - set(v)
        if missing or any(w < 0 for w in v.values()):
            raise ValueError(f"weights need non-negative {', '.join(COMPONENTS)}")
        return v


@lru_cache
def get_scoring_settings() -> ScoringSettings:
    return ScoringSettings()
