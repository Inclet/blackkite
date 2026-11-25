"""Validate rules without a database: windows, status, conflicts, trust states."""

from datetime import UTC, datetime, timedelta

import pytest

from blackkite.pipeline.dates import parse_date
from blackkite.pipeline.validate import (
    SourceDeadline,
    check_date,
    resolve_deadline,
    status_for,
    trust_state,
    verification_for,
)

NOW = datetime(2026, 11, 25, 8, tzinfo=UTC)


@pytest.mark.parametrize(
    ("field", "text", "status"),
    [
        ("published_at", "2026-11-20", "ok"),
        ("published_at", "2026-11-27", "out_of_window"),  # more than a day ahead
        ("published_at", "2025-06-01", "ok"),
        ("published_at", "2025-05-01", "out_of_window"),  # over 18 months old
        ("deadline_at", "2027-12-31", "ok"),
        ("deadline_at", "2029-01-01", "out_of_window"),  # over 2 years ahead
        ("deadline_at", "2025-12-01", "ok"),  # passed, but plausible: expired
        ("deadline_at", "2025-11-01", "out_of_window"),  # over a year ago
        ("event_start", "25 November", "no_year"),
        ("deadline_at", "TBC", "unparsed"),
    ],
)
def test_plausible_windows(field, text, status):
    c = check_date(field, parse_date(text, "end"), NOW)
    assert c.status == status
    assert (c.value is None) == (status != "ok")
    if status != "ok":
        assert c.raw == text


def test_status_rules():
    d = lambda days: NOW + timedelta(days=days)
    assert status_for("open", "tender", d(-0.01), None, None, NOW) == "expired"
    assert status_for("open", "tender", d(7), None, None, NOW) == "closing_soon"
    assert status_for("open", "tender", d(7.1), None, None, NOW) == "open"
    assert status_for("open", "tender", None, None, None, NOW) == "open"
    assert status_for("open", "event", None, d(-3), d(-1), NOW) == "expired"
    assert status_for("open", "event", None, d(3), None, NOW) == "closing_soon"
    assert status_for("awarded", "tender", d(-30), None, None, NOW) == "awarded"
    assert status_for("expired", "tender", d(30), None, None, NOW) == "open"


def test_resolve_deadline_prefers_original_then_earliest():
    a = datetime(2026, 11, 30, 15, tzinfo=UTC)
    b = datetime(2026, 12, 2, 15, tzinfo=UTC)
    assert resolve_deadline(
        [SourceDeadline("agg", False, a), SourceDeadline("orig", True, b)]
    ) == (
        b,
        True,
        "original",
    )
    assert resolve_deadline(
        [SourceDeadline("p", False, b), SourceDeadline("n", False, a)]
    ) == (
        a,
        True,
        "earliest",
    )
    # Same Kigali day, different times: not a conflict.
    same = datetime(2026, 11, 30, 21, 59, tzinfo=UTC)
    assert (
        resolve_deadline(
            [SourceDeadline("p", False, a), SourceDeadline("n", False, same)]
        )[1]
        is False
    )
    assert resolve_deadline([]) == (None, False, None)


def test_verification_and_trust_states():
    assert (
        verification_for([(True, "original"), (False, "aggregator")])
        == "verified_original"
    )
    assert (
        verification_for([(False, "aggregator"), (False, "aggregator")])
        == "aggregator_only"
    )
    assert (
        verification_for([(False, "publisher"), (False, "aggregator")]) == "unverified"
    )
    assert verification_for([]) == "unverified"
    assert trust_state("verified_original", {}) == "confirmed"
    assert trust_state("aggregator_only", {}) == "unconfirmed"
    assert trust_state("unverified", {"_deadline_conflict": False}) == "unconfirmed"
    assert trust_state("verified_original", {"_deadline_conflict": True}) == "conflict"
    assert trust_state("aggregator_only", {"_deadline_conflict": True}) == "conflict"


def test_mismatch_is_reviewable():
    from blackkite.pipeline.dates import parse_extracted_date
    from blackkite.pipeline.validate import check_date, review_reason

    check = check_date(
        "deadline_at",
        parse_extracted_date("2026-12-30", "Bids close on 30 November 2026."),
        NOW,
    )
    assert check.reviewable and check.value is None
    assert "not stated in its snippet" in review_reason("deadline_at", check)
