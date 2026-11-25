"""Hard filters, rule flags and components (spec 7, 7.1), without a database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from blackkite.db.models import Opportunity, Profile
from blackkite.scoring.fitword import fit_word
from blackkite.scoring.rules import (
    CarryingSource,
    check_rules,
    outside_rwanda,
    source_score,
    time_score,
)
from blackkite.scoring.settings import FitWordRule, ScoringSettings
from blackkite.seed.loader import load_seed_profiles

NOW = datetime(2026, 11, 25, 8, tzinfo=UTC)
S = ScoringSettings(_env_file=None)


def seed(name: str) -> Profile:
    entry = next(p for p in load_seed_profiles()["profiles"] if p["name"] == name)
    data = {k: v for k, v in entry.items() if k not in ("name", "type")}
    return Profile(id=uuid.uuid4(), name=name, type=entry["type"], data=data, version=1)


def opp(title="Transport of goods", stream="tender", **kw) -> Opportunity:
    kw.setdefault("status", "open")
    kw.setdefault("verification", "verified_original")
    kw.setdefault("evidence", {})
    kw.setdefault("tags", [])
    kw.setdefault("deadline_at", NOW + timedelta(days=30))
    if kw.get("value_amount") is not None:
        kw["value_amount"] = Decimal(str(kw["value_amount"]))
    return Opportunity(id=uuid.uuid4(), stream=stream, title=title, **kw)


def src(kind="original", muted=False, home="https://notices.example.org"):
    return CarryingSource("S", kind, home, home + "/n/1", kind == "original", muted)


IRONJI = seed("Ironji-Trade")
AI_LAB = seed("AI lab")
PERSONAL = seed("Personal")


def rules(o, p=IRONJI, sources=None, docs=()):
    return check_rules(o, p, [src()] if sources is None else sources, list(docs), NOW)


def codes(r):
    return [f.code for f in r.flags]


# --- hard filters ------------------------------------------------------------------


def test_deadline_passed():
    assert (
        rules(opp(deadline_at=NOW - timedelta(hours=1))).hard_filtered
        == "deadline_passed"
    )
    assert rules(opp(status="expired")).hard_filtered == "deadline_passed"
    ended = opp(stream="event", deadline_at=None, event_start=NOW - timedelta(days=2))
    assert rules(ended).hard_filtered == "deadline_passed"


@pytest.mark.parametrize(
    "location,outside",
    [
        ("Nairobi, Kenya", True),
        ("Kampala", True),
        ("Kigali, Rwanda", False),
        ("Kigali and Nairobi", False),
        ("Online", False),
        ("East Africa region", False),
        (None, False),
    ],
)
def test_outside_rwanda(location, outside):
    assert outside_rwanda(location) is outside
    r = rules(opp(location=location))
    assert (r.hard_filtered == "outside_rwanda") is outside


def test_stream_not_selected_and_missing_streams_never_filter():
    assert rules(opp(stream="investment")).hard_filtered == "stream_not_selected"
    no_streams = seed("Ironji-Trade")
    no_streams.data = {**no_streams.data, "streams": None}
    assert rules(opp(stream="investment"), no_streams).hard_filtered is None


def test_muted_source_only():
    o = opp()
    assert rules(o, sources=[src(muted=True)]).hard_filtered == "muted_source_only"
    assert rules(o, sources=[src(muted=True), src("publisher")]).hard_filtered is None
    assert rules(o, sources=[]).hard_filtered is None  # private item: no sources


@pytest.mark.parametrize(
    "eligibility",
    [
        "This call is open only to registered NGOs operating in Rwanda.",
        "Eligible applicants: local civil society organisations only.",
        "Restricted to non-profit organisations.",
        "For-profit companies are not eligible.",
    ],
)
def test_ngo_only_is_ineligible_for_a_business(eligibility):
    o = opp(stream="funding", eligibility=eligibility)
    r = rules(o)
    assert r.hard_filtered == "ineligible"
    ngo = seed("AI lab")
    ngo.data = {**ngo.data, "organisation_type": "ngo"}
    assert rules(o, ngo).hard_filtered is None


def test_ngo_mentioned_but_not_exclusive_does_not_filter():
    o = opp(eligibility="Companies, NGOs and cooperatives may apply.")
    assert rules(o).hard_filtered is None


def test_capacity_threshold_above_stated_capacity_is_ineligible():
    above = opp(requirements=["The bidder must have at least 150 refrigerated trucks."])
    r = rules(above)
    assert r.hard_filtered == "ineligible" and "150" in r.filter_reason
    # Volume within the partner network: met (spec 7.1).
    within = opp(requirements=["A minimum of 50 trucks available for the contract."])
    assert rules(within).hard_filtered is None
    assert "check_capacity" not in codes(rules(within))


def test_missing_capacity_never_filters_but_flags():
    # AI lab states no capacity at all; Ironji states no tonnage.
    trucks = opp(requirements=["Access to at least 20 trucks."])
    r = rules(trucks, AI_LAB)
    assert r.hard_filtered is None and "check_capacity" in codes(r)
    tonnage = opp(requirements=["Vehicles with a capacity of at least 30 tonnes."])
    r = rules(tonnage)
    assert r.hard_filtered is None and "check_capacity" in codes(r)


def test_min_value_only_when_stated_in_rwf():
    low = opp(value_amount=3_000_000, value_currency="RWF")
    r = rules(low)
    assert r.hard_filtered == "below_min_value"
    assert "FRW 3,000,000" in r.filter_reason and "FRW 5,000,000" in r.filter_reason
    assert (
        rules(opp(value_amount=6_000_000, value_currency="RWF")).hard_filtered is None
    )
    assert rules(opp(value_amount=3_000, value_currency="USD")).hard_filtered is None
    unknown = rules(opp())
    assert unknown.hard_filtered is None and "value_unknown" in codes(unknown)
    # AI lab has no minimum (null): no filter and no "value unknown" flag.
    assert (
        rules(opp(value_amount=1000, value_currency="RWF"), AI_LAB).hard_filtered
        is None
    )
    assert "value_unknown" not in codes(rules(opp(), AI_LAB))


# --- 7.1 flags -----------------------------------------------------------------------


def test_owned_fleet_flag_quotes_the_requirement():
    o = opp(requirements=["Copies of vehicle logbooks for each truck proposed."])
    r = rules(o)
    assert r.hard_filtered is None
    [f] = [f for f in r.flags if f.code == "owned_fleet"]
    assert f.label == "May require owned fleet"
    assert "logbooks" in f.quote and f.quote in o.requirements[0]
    assert f.quote in f.to_check


@pytest.mark.parametrize(
    "text",
    [
        "Vehicle registration cards in the name of the bidder.",
        "Trucks must be owned by the bidder.",
        "Proof of vehicle ownership.",
        "The bidder must own at least 10 trucks.",
    ],
)
def test_owned_fleet_variants(text):
    r = rules(opp(requirements=[text]))
    assert r.hard_filtered is None
    assert "owned_fleet" in codes(r)


def test_owned_fleet_not_flagged_when_profile_owns_trucks():
    owner = seed("Ironji-Trade")
    owner.data = {
        **owner.data,
        "capacity": {**owner.data["capacity"], "owned_trucks": 12},
    }
    r = rules(opp(requirements=["Copies of vehicle logbooks."]), owner)
    assert "owned_fleet" not in codes(r)
    # A stated owned fleet below an ownership threshold is a capacity shortfall.
    r = rules(opp(requirements=["The bidder must own at least 20 trucks."]), owner)
    assert r.hard_filtered == "ineligible"


def test_transport_licence_flag():
    o = opp(eligibility="A valid transport operator licence issued by RURA.")
    [f] = [f for f in rules(o).flags if f.code == "transport_licence"]
    assert f.label == "Requires transport licence"
    assert "transport operator licence" in f.quote


def test_umucyo_flag_by_source_and_by_text():
    umucyo = CarryingSource(
        "Umucyo",
        "original",
        "https://umucyo.gov.rw",
        "https://umucyo.gov.rw/n/1",
        True,
        False,
    )
    r = rules(opp(), sources=[umucyo])
    [f] = [f for f in r.flags if f.code == "umucyo_registration"]
    assert f.label == "Needs Umucyo supplier registration"
    by_text = opp(
        submission_method="Bids are submitted through the Umucyo e-procurement system."
    )
    assert "umucyo_registration" in codes(rules(by_text))
    # The flag goes once the profile lists an account.
    holder = seed("Ironji-Trade")
    holder.data = {
        **holder.data,
        "registrations_held": [
            *holder.data["registrations_held"],
            "Umucyo supplier account",
        ],
    }
    assert "umucyo_registration" not in codes(rules(opp(), holder, sources=[umucyo]))


def test_flags_display_order():
    o = opp(
        requirements=["Copies of vehicle logbooks.", "A valid transport licence."],
        submission_method="Submit through Umucyo.",
    )
    assert codes(rules(o)) == [
        "owned_fleet",
        "transport_licence",
        "umucyo_registration",
        "value_unknown",
    ]


def test_events_and_investments_get_no_business_flags():
    ev = opp(
        "Logistics summit",
        stream="event",
        deadline_at=None,
        event_start=NOW + timedelta(days=20),
    )
    assert rules(ev).flags == []


# --- components ------------------------------------------------------------------


def test_time_penalises_short_and_unknown():
    soon = time_score(opp(deadline_at=NOW + timedelta(days=1)), NOW, S)
    mid = time_score(opp(deadline_at=NOW + timedelta(days=10)), NOW, S)
    far = time_score(opp(deadline_at=NOW + timedelta(days=40)), NOW, S)
    unknown = time_score(opp(deadline_at=None), NOW, S)
    assert soon < unknown < mid < far == 1.0
    ev = opp(stream="event", deadline_at=None, event_start=NOW + timedelta(days=30))
    assert time_score(ev, NOW, S) == 1.0


def test_source_score_orders_verification_and_kind():
    def score(ver, kinds, trust=None):
        o = opp(verification=ver, evidence={"_trust": trust} if trust else {})
        return source_score(o, [src(k) for k in kinds], S)

    assert score("verified_original", ["original"]) == pytest.approx(1.0)
    assert (
        score("verified_original", ["original"])
        > score("unverified", ["publisher"])
        > score("aggregator_only", ["aggregator"])
    )
    assert score("unverified", ["publisher"], "conflict") < score(
        "unverified", ["publisher"]
    )


# --- fit word ---------------------------------------------------------------------

R = FitWordRule()


@pytest.mark.parametrize(
    "fit,elig,word",
    [
        (0.8, 0.8, "strong"),
        (0.7, 0.7, "strong"),
        (0.65, 0.55, "good"),
        (0.9, 0.6, "good"),  # misses strong only on eligibility
        (0.6, 0.5, "good"),
        (0.9, 0.49, "possible"),
        (0.59, 0.9, "possible"),
        (0.45, 0.1, "possible"),
        (0.39, 0.9, None),
    ],
)
def test_fit_word_contract_rule(fit, elig, word):
    assert fit_word(R, fit=fit, eligibility=elig, stream="tender") == word


def test_fit_word_config_and_caps():
    strict = FitWordRule(strong_eligibility=0.95)
    assert fit_word(strict, fit=0.9, eligibility=0.9, stream="funding") == "good"
    assert (
        fit_word(R, fit=0.9, eligibility=0.9, stream="tender", cap="possible")
        == "possible"
    )
    for stream in ("event", "investment"):
        assert fit_word(R, fit=1, eligibility=1, stream=stream) is None
