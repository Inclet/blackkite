"""Rules reasons quote what actually matched (M5 fix list 2), without a database."""

from __future__ import annotations

import uuid

from blackkite.db.models import Opportunity, Profile
from blackkite.scoring.match import match
from blackkite.scoring.service import _rules_reason
from blackkite.scoring.settings import ScoringSettings
from blackkite.scoring.text import mentioned, term_hits
from tests.scoring.test_rules import IRONJI, opp

S = ScoringSettings(_env_file=None)


def profile(**data) -> Profile:
    return Profile(id=uuid.uuid4(), name="P", type="business", data=data, version=1)


def reason(o: Opportunity, p: Profile) -> str:
    return _rules_reason(o, match(o, p, None, S))


def test_ironji_vaccine_cold_chain_claims_only_cold_chain():
    o = opp(
        "Cold chain transport of vaccines to district hospitals",
        subtype="request for bids",
        tags=["service:cold chain transport", "sector:health"],
        summary="Refrigerated transport from a central store to district hospitals.",
    )
    m = match(o, IRONJI, None, S)
    assert m.shortlisted
    # "dry freight" and "last-mile distribution" are not in the notice: only
    # cold chain is claimed; transport is said, never as a listed service.
    assert m.phrases == ["cold chain"]
    assert "district" not in m.matched  # not "distribution"
    text = reason(o, IRONJI)
    assert text == (
        "It mentions cold chain, which this profile lists, and also transport."
    )
    assert "dry freight" not in text and "last-mile" not in text


def test_duplicate_terms_quote_the_item_word_once():
    p = profile(services=["community health"], sectors=["health"])
    o = opp("Supply of health kits to clinics", tags=["sector:health"])
    assert reason(o, p) == "It mentions health, which this profile lists."
    o2 = opp("Community health worker training", tags=["sector:health"])
    assert reason(o2, p) == "It mentions community health, which this profile lists."


def test_multi_word_service_not_claimed_from_one_word():
    p = profile(services=["community health"])
    o = opp("Construction of a health centre")
    m = match(o, p, None, S)
    assert m.phrases == []
    assert reason(o, p) == "It mentions health, close to what this profile lists."


def test_weak_words_alone_never_match():
    p = profile(services=["dry freight", "cold chain", "last-mile distribution"])
    for title in (
        "Supply of dry foodstuffs",
        "Supply chain audit",
        "Last call for cold weather clothing",
        "District office stationery",
    ):
        assert term_hits(p.data["services"], title) == [], title


def test_synonym_phrase_is_a_phrase_hit():
    [hit] = term_hits(["cold chain"], "Refrigerated logistics for dairy")
    assert hit.phrase and not hit.literal
    assert hit.quotes == ("refrigerated logistics",)


def test_phrase_does_not_span_tags_or_sentences():
    # Both words are weak alone, so split across a break nothing matches.
    assert term_hits(["cold chain"], "Supply of cold\nchain saws") == []
    assert term_hits(["cold chain"], "Too cold. Chain link fence") == []
    [hit] = term_hits(["dry freight"], "Dry\nfreight forwarding")
    assert not hit.phrase and hit.quotes == ("freight",)


def test_mentioned_keeps_acronyms_and_dedupes():
    hits = term_hits(["ICT", "software", "ict services"], "Supply of ICT equipment")
    assert mentioned(hits) == ["ICT"]


def test_event_reason_joins_with_and():
    p = Profile(
        id=uuid.uuid4(),
        name="Personal",
        type="personal",
        data={"event_topics": ["AI and tech", "finance and fintech"]},
        version=1,
    )
    o = opp("Fintech and AI summit", stream="event", tags=["sector:fintech"])
    assert reason(o, p).endswith(", on AI and fintech.")
