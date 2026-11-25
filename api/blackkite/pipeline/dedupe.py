"""Stage 3, dedupe: find the catalogue record an incoming item belongs to.

Two ways to match, never across streams and never onto a private manual item:

1. **Exact**: the item's canonical URL (or detail URL) is already a carrying URL of
   an opportunity.
2. **Similar**: normalised (organisation, title) similarity plus a compatible
   deadline. Similarity is rapidfuzz ``token_sort_ratio`` (0-100) on keys that are
   casefolded, NFKC-normalised, punctuation-free; organisation keys also drop legal
   suffixes (Ltd, Limited, PLC...) and an acronym equal to the other name's
   initials counts as 100 ("RTDA" vs "Rwanda Transport Development Agency").

   Thresholds:

   * title >= ``TITLE_MIN`` (90) and organisation >= ``ORG_MIN`` (85) when both
     organisations are known;
   * title >= ``TITLE_MIN_STRICT`` (95) when either organisation is unknown or
     either deadline is unknown;
   * deadlines, when both known, within ``DEADLINE_WINDOW`` (14 days) of each other.
     A difference inside the window merges the records and is then a *conflict*
     (validate sets needs_review); further apart they are treated as different
     notices (a re-advertisement, the next round);
   * generic titles ("Invitation for Bids", "Tender notice", or keys under 16
     characters; spec 2.4) match only with both organisations matching and both
     deadlines on the same day.

   Each candidate is compared on every title and organisation any of its sources
   listed (kept in ``evidence["_sources"]``), not only the cleaned record title.

Candidates are public opportunities in the stream(s) whose deadline is unknown or
not more than 30 days past and that were created in the last 400 days.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import sqlalchemy as sa
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from blackkite.db.models import Opportunity, OpportunitySource
from blackkite.pipeline.dates import kigali_date

TITLE_MIN = 90
TITLE_MIN_STRICT = 95
ORG_MIN = 85
DEADLINE_WINDOW = timedelta(days=14)
CANDIDATE_DEADLINE_PAST = timedelta(days=30)
CANDIDATE_AGE = timedelta(days=400)
GENERIC_MIN_LEN = 16

GENERIC_TITLES = {
    "invitation for bids",
    "invitation to bid",
    "invitation for tenders",
    "tender notice",
    "tender",
    "tenders",
    "call for bids",
    "call for proposals",
    "request for proposals",
    "request for quotations",
    "expression of interest",
    "request for expression of interest",
    "tenders for various items",
    "procurement notice",
    "public notice",
    "notice",
}
_LEGAL = {"ltd", "limited", "plc", "inc", "llc", "co", "company", "the", "sarl", "srl"}
_INITIAL_SKIP = {"of", "and", "the", "for", "in", "de", "du", "des", "la", "le", "&"}
_NON_ALNUM = re.compile(r"[^\w]+")


def title_key(text: str | None) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text).casefold().replace("_", " ")
    return " ".join(_NON_ALNUM.sub(" ", t).split())


def org_key(text: str | None) -> str:
    return " ".join(w for w in title_key(text).split() if w not in _LEGAL)


def _initials(key: str) -> str:
    return "".join(w[0] for w in key.split() if w not in _INITIAL_SKIP)


def org_similarity(a: str | None, b: str | None) -> float | None:
    ka, kb = org_key(a), org_key(b)
    if not ka or not kb:
        return None
    if ka == kb:
        return 100.0
    for short, long in ((ka, kb), (kb, ka)):
        if " " not in short and len(short) >= 2 and _initials(long) == short:
            return 100.0
    return float(fuzz.token_sort_ratio(ka, kb))


def is_generic(key: str) -> bool:
    return key in GENERIC_TITLES or len(key) < GENERIC_MIN_LEN


@dataclass(frozen=True, slots=True)
class Match:
    opportunity: Opportunity
    how: Literal["url", "similar"]
    title_score: float = 100.0
    org_score: float | None = None


def deadlines_compatible(a: datetime | None, b: datetime | None) -> bool | None:
    """True/False when both known, None when either is unknown."""
    if a is None or b is None:
        return None
    return abs(a - b) <= DEADLINE_WINDOW


def similar(
    title: str,
    organisation: str | None,
    deadline: datetime | None,
    c_titles: list[str],
    c_orgs: list[str],
    c_deadline: datetime | None,
) -> tuple[float, float | None] | None:
    """(title score, org score) when the item matches the candidate, else None."""
    key = title_key(title)
    if not key:
        return None
    t_score = max(
        (float(fuzz.token_sort_ratio(key, title_key(t))) for t in c_titles), default=0.0
    )
    o_scores = [
        s for s in (org_similarity(organisation, o) for o in c_orgs) if s is not None
    ]
    o_score = max(o_scores) if o_scores else None
    if o_score is not None and o_score < ORG_MIN:
        return None
    compat = deadlines_compatible(deadline, c_deadline)
    if compat is False:
        return None
    generic = is_generic(key) or all(is_generic(title_key(t)) for t in c_titles)
    if generic:
        if (
            o_score is None
            or deadline is None
            or c_deadline is None
            or kigali_date(deadline) != kigali_date(c_deadline)
            or t_score < TITLE_MIN
        ):
            return None
        return t_score, o_score
    strict = o_score is None or compat is None
    if t_score < (TITLE_MIN_STRICT if strict else TITLE_MIN):
        return None
    return t_score, o_score


def find_by_url(session: Session, urls: list[str], streams: list[str]) -> Match | None:
    urls = [u for u in urls if u]
    if not urls:
        return None
    opp = session.scalars(
        sa.select(Opportunity)
        .join(OpportunitySource, OpportunitySource.opportunity_id == Opportunity.id)
        .where(
            OpportunitySource.url.in_(urls),
            Opportunity.stream.in_(streams),
            Opportunity.visibility == "public",
        )
        .order_by(Opportunity.created_at)
        .limit(1)
    ).first()
    return Match(opp, "url") if opp else None


def _known_titles_orgs(opp: Opportunity) -> tuple[list[str], list[str]]:
    titles = [opp.title]
    orgs = [o for o in (opp.organisation, opp.organisation_short) if o]
    for entry in (opp.evidence or {}).get("_sources", {}).values():
        if entry.get("title"):
            titles.append(entry["title"])
        if entry.get("organisation"):
            orgs.append(entry["organisation"])
    return list(dict.fromkeys(titles)), list(dict.fromkeys(orgs))


def find_similar(
    session: Session,
    *,
    title: str,
    organisation: str | None,
    deadline: datetime | None,
    streams: list[str],
    now: datetime,
) -> Match | None:
    candidates = session.scalars(
        sa.select(Opportunity).where(
            Opportunity.stream.in_(streams),
            Opportunity.visibility == "public",
            Opportunity.created_at >= now - CANDIDATE_AGE,
            sa.or_(
                Opportunity.deadline_at.is_(None),
                Opportunity.deadline_at >= now - CANDIDATE_DEADLINE_PAST,
            ),
        )
    ).all()
    best: Match | None = None
    for opp in candidates:
        titles, orgs = _known_titles_orgs(opp)
        scores = similar(title, organisation, deadline, titles, orgs, opp.deadline_at)
        if scores is None:
            continue
        m = Match(opp, "similar", scores[0], scores[1])
        if best is None or (m.title_score, m.org_score or 0) > (
            best.title_score,
            best.org_score or 0,
        ):
            best = m
    return best
