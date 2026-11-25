"""The fit word shown in the list (spec 12: a word with a reason, never a score).

Rule: docs/api-contract.md section 1, thresholds in ``ScoringSettings.fit_word``.
Investments and events never get one (decision 24, spec 7.1).
"""

from __future__ import annotations

from typing import Literal

from blackkite.scoring.settings import FitWordRule

FitWord = Literal["strong", "good", "possible"]
FIT_WORD_STREAMS = ("tender", "funding")
_ORDER = (None, "possible", "good", "strong")


def fit_word(
    rule: FitWordRule,
    *,
    fit: float,
    eligibility: float,
    stream: str,
    cap: FitWord | None = None,
) -> FitWord | None:
    if stream not in FIT_WORD_STREAMS:
        return None
    word: FitWord | None = None
    if fit >= rule.strong_fit and eligibility >= rule.strong_eligibility:
        word = "strong"
    elif fit >= rule.good_fit and eligibility >= rule.good_eligibility:
        word = "good"
    elif fit >= rule.possible_fit:
        word = "possible"
    if cap is not None and _ORDER.index(word) > _ORDER.index(cap):
        word = cap
    return word
