"""Row factories for member API, digest and alert tests.

Score rows are written in exactly the shape of docs/api-contract.md section 1
(the scoring track writes them in production).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from blackkite.db.models import (
    Opportunity,
    OpportunitySource,
    Profile,
    Source,
    User,
    UserOpportunity,
    UserOpportunityScore,
)

KIGALI = timezone(timedelta(hours=2))
# The frozen clock of the design boards: Tuesday 24 Nov 2026, 14:00 Kigali.
NOW = datetime(2026, 11, 24, 14, 0, tzinfo=KIGALI)


def kigali(y: int, m: int, d: int, h: int = 17, mi: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=KIGALI)


def source(
    db: Session,
    name: str,
    *,
    status: str = "active",
    kind: str = "publisher",
    publisher: str | None = None,
    streams: list[str] | None = None,
) -> Source:
    s = Source(
        name=name,
        home_url=f"https://{name.lower().replace(' ', '')}.example/",
        publisher=publisher,
        streams=streams or ["tender", "investment", "funding", "event"],
        kind=kind,
        collector_type="html_list",
        config={},
        status=status,
    )
    db.add(s)
    db.flush()
    return s


def opportunity(db: Session, title: str = "Item", **kw: Any) -> Opportunity:
    kw.setdefault("stream", "tender")
    kw.setdefault("organisation", "Some Org")
    kw.setdefault("status", "open")
    o = Opportunity(title=title, **kw)
    db.add(o)
    db.flush()
    return o


def link(
    db: Session,
    opp: Opportunity,
    src: Source,
    url: str | None = None,
    *,
    is_original: bool = False,
    first_seen: datetime | None = None,
) -> OpportunitySource:
    first_seen = first_seen or NOW - timedelta(days=3)
    ln = OpportunitySource(
        opportunity_id=opp.id,
        source_id=src.id,
        url=url or f"https://example.org/{opp.id}",
        is_original=is_original,
        first_seen=first_seen,
        last_seen=first_seen + timedelta(days=1),
    )
    db.add(ln)
    db.flush()
    return ln


def profile(
    db: Session, user: User, name: str, type: str = "business", **data: Any
) -> Profile:
    data.setdefault("streams", ["tender", "funding", "event"])
    p = Profile(user_id=user.id, name=name, type=type, data=data)
    db.add(p)
    db.flush()
    return p


def breakdown(
    *,
    fit_word: str | None = "strong",
    reasons: list[str] | None = None,
    flags: list[dict[str, str]] | None = None,
    hard_filtered: str | None = None,
    fit_confidence: float = 0.8,
    eligibility_confidence: float = 0.8,
) -> dict[str, Any]:
    return {
        "version": 1,
        "components": {
            "fit": 30,
            "eligibility": 15,
            "value": 10,
            "time": 10,
            "source": 5,
        },
        "fit_confidence": fit_confidence,
        "eligibility_confidence": eligibility_confidence,
        "fit_word": fit_word,
        "reasons": reasons or [],
        "flags": flags or [],
        "provisional": False,
        "hard_filtered": hard_filtered,
        "model": "claude-haiku-5-5",
        "prompt_version": "score-v1",
        "scored_at": NOW.isoformat(),
    }


def score(
    db: Session,
    user: User,
    opp: Opportunity,
    prof: Profile,
    value: int = 70,
    reason: str | None = None,
    **bd: Any,
) -> UserOpportunityScore:
    s = UserOpportunityScore(
        user_id=user.id,
        opportunity_id=opp.id,
        profile_id=prof.id,
        score=value,
        score_reason=reason,
        score_breakdown=breakdown(**bd),
    )
    db.add(s)
    db.flush()
    return s


def state(
    db: Session, user: User, opp: Opportunity, st: str, note: str | None = None
) -> UserOpportunity:
    uo = UserOpportunity(user_id=user.id, opportunity_id=opp.id, state=st, note=note)
    db.add(uo)
    db.flush()
    return uo
