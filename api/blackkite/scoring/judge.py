"""The one model judgement per shortlisted (profile, opportunity) pair (spec 7).

Forced structured output (``record_judgement``). The reply is checked before use:

* ``quote`` must occur in the notice text the model was shown (after whitespace,
  quote and dash normalisation, case-insensitive). If it does not, the reason is
  rejected, both confidences are capped at ``UNSUPPORTED_CAP`` (at most
  "possible"), and the pair's reason falls back to the rules' reason;
* the reason is cut to one sentence; when it does not carry the quote, the quote
  is appended;
* each flag needs a supported quote, or it is dropped; at most three are kept;
  labels are fixed per kind (never model text in a row subtitle).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from blackkite.db.models import Opportunity, Profile
from blackkite.llm.client import LLMClient
from blackkite.llm.prompt import load_prompt
from blackkite.pipeline.extract import first_sentences, normalise_for_match
from blackkite.scoring.rules import Flag
from blackkite.scoring.text import clean_quote, quote_supported

PROMPT_VERSION = "score-v1"
TOOL_NAME = "record_judgement"
TOOL_DESCRIPTION = (
    "Record how well the notice fits the profile, with the quoted requirement "
    "behind the judgement."
)
UNSUPPORTED_CAP = 0.5
MAX_FLAGS = 3
MAX_REASON_CHARS = 400

FlagKind = Literal[
    "registration", "capacity", "experience", "documents", "eligibility", "other"
]
MODEL_FLAG_LABELS: dict[str, str] = {
    "registration": "Check registration",
    "capacity": "Check capacity",
    "experience": "Check experience",
    "documents": "Check documents",
    "eligibility": "Check eligibility",
    "other": "Check the notice",
}
# Codes of model flags; disjoint from rules.RULE_FLAGS so a stored row can be split.
MODEL_FLAG_CODES = {k: f"model_{k}" for k in MODEL_FLAG_LABELS}


class JudgementFlag(BaseModel):
    kind: FlagKind = "other"
    quote: str
    to_check: str


class JudgementReply(BaseModel):
    fit_confidence: float = Field(ge=0, le=1)
    eligibility_confidence: float = Field(ge=0, le=1)
    reason: str
    quote: str
    flags: list[JudgementFlag] = Field(default_factory=list)


@dataclass
class Judgement:
    fit_confidence: float
    eligibility_confidence: float
    reason: str | None  # None when rejected
    flags: list[Flag] = field(default_factory=list)
    model: str | None = None
    prompt_version: str = PROMPT_VERSION
    rejected: list[str] = field(default_factory=list)


PROFILE_PROMPT_FIELDS = (
    "streams",
    "location",
    "services",
    "sectors",
    "registrations_held",
    "registrations_not_held",
    "capacity",
    "min_contract_rwf",
    "instruments",
    "ticket_range_rwf",
    "event_topics",
    "exclusions",
    "provisional",
    "organisation_type",
    # Read by the model only; no rule uses them yet.
    "locations",
    "horizon",
    "availability",
    "budget_rwf",
)


def profile_for_prompt(profile: Profile) -> dict[str, Any]:
    data = profile.data or {}
    out: dict[str, Any] = {"name": profile.name, "type": profile.type}
    for k in PROFILE_PROMPT_FIELDS:
        if k in data:
            out[k] = data[k]
    return out


def _fmt_dt(v) -> str | None:
    return v.date().isoformat() if v is not None else None


def build_user_message(
    opp: Opportunity, profile: Profile, notice: str, rule_flags: list[Flag]
) -> str:
    facts = {
        "stream": opp.stream,
        "subtype": opp.subtype,
        "deadline": _fmt_dt(opp.deadline_at),
        "value": (
            f"{opp.value_amount} {opp.value_currency or ''}".strip()
            if opp.value_amount is not None
            else None
        ),
    }
    flags = [{"label": f.label, "quote": f.quote} for f in rule_flags]
    return (
        f"<profile>\n{json.dumps(profile_for_prompt(profile), ensure_ascii=False, indent=1)}\n</profile>\n"
        f"<facts>\n{json.dumps(facts, ensure_ascii=False)}\n</facts>\n"
        f"<rule_flags>\n{json.dumps(flags, ensure_ascii=False)}\n</rule_flags>\n"
        f"<our_summary>\n{opp.summary or ''}\n</our_summary>\n"
        f"<notice>\n{notice}\n</notice>"
    )


def check_judgement(reply: JudgementReply, notice: str, model: str | None) -> Judgement:
    src = normalise_for_match(notice)
    out = Judgement(
        fit_confidence=float(reply.fit_confidence),
        eligibility_confidence=float(reply.eligibility_confidence),
        reason=None,
        model=model,
    )
    quote = reply.quote.strip()
    if quote_supported(quote, src):
        reason = first_sentences(normalise_for_match(reply.reason), 1)[
            :MAX_REASON_CHARS
        ]
        nq = clean_quote(quote)
        if nq.lower() not in reason.lower():
            reason = f"{reason.rstrip('.')}: “{nq}”."
        out.reason = reason
    else:
        out.rejected.append("reason")
        out.fit_confidence = min(out.fit_confidence, UNSUPPORTED_CAP)
        out.eligibility_confidence = min(out.eligibility_confidence, UNSUPPORTED_CAP)
    for f in reply.flags:
        if len(out.flags) >= MAX_FLAGS:
            break
        if not quote_supported(f.quote, src):
            out.rejected.append("flag")
            continue
        out.flags.append(
            Flag(
                MODEL_FLAG_CODES[f.kind],
                MODEL_FLAG_LABELS[f.kind],
                clean_quote(f.quote),
                first_sentences(normalise_for_match(f.to_check), 1)[:MAX_REASON_CHARS],
            )
        )
    return out


def judge(
    llm: LLMClient,
    opp: Opportunity,
    profile: Profile,
    notice: str,
    rule_flags: list[Flag],
) -> Judgement:
    """One call. Raises LLMError; the caller falls back to a rules-only score."""
    prompt = load_prompt(PROMPT_VERSION)
    reply = llm.structured(
        system=prompt.text,
        user=build_user_message(opp, profile, notice, rule_flags),
        schema=JudgementReply,
        tool_name=TOOL_NAME,
        tool_description=TOOL_DESCRIPTION,
    )
    out = check_judgement(reply, notice, llm.model)
    out.prompt_version = prompt.version
    return out
