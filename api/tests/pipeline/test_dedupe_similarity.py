"""Similarity rules for dedupe, without a database."""

from datetime import UTC, datetime, timedelta

from blackkite.pipeline.dedupe import org_similarity, similar, title_key

D = datetime(2026, 12, 10, 15, tzinfo=UTC)


def test_keys_ignore_case_punctuation_and_legal_suffixes():
    assert (
        title_key("TENDER: Supply of Cold-Chain   Trucks!")
        == "tender supply of cold chain trucks"
    )
    assert org_similarity("Example Logistics Ltd.", "EXAMPLE LOGISTICS LIMITED") == 100
    assert org_similarity("RTDA", "Rwanda Transport Development Agency") == 100
    assert org_similarity("Example Agency", None) is None


def test_near_duplicate_titles_match():
    assert similar(
        "SUPPLY OF COLD-CHAIN TRANSPORT SERVICES FOR VACCINES",
        "Example Districts Agency Ltd",
        D,
        ["Supply of cold chain transport services for vaccines"],
        ["Example Districts Agency"],
        D + timedelta(days=2),
    )


def test_different_organisation_or_far_deadline_does_not_match():
    t = "Supply of cold chain transport services for vaccines"
    assert (
        similar(t, "Another Ministry", D, [t], ["Example Districts Agency"], D) is None
    )
    assert (
        similar(
            t,
            "Example Districts Agency",
            D,
            [t],
            ["Example Districts Agency"],
            D + timedelta(days=40),
        )
        is None
    )


def test_unknown_org_or_deadline_needs_a_stricter_title_match():
    a = "Supply of cold chain transport services for vaccines"
    b = "Supply of cold chain transport services for vaccines, Lot 2"  # ~94.5
    assert similar(
        a, "Example Districts Agency", D, [b], ["Example Districts Agency"], D
    )
    assert similar(a, None, D, [b], ["Example Districts Agency"], D) is None
    assert (
        similar(
            a, "Example Districts Agency", None, [b], ["Example Districts Agency"], D
        )
        is None
    )
    assert similar(a, None, None, [a], [], None)


def test_generic_titles_need_same_org_and_same_day():
    g = "Invitation for Bids"
    org = ["Example Districts Agency"]
    assert similar(g, "Example Districts Agency", D, [g], org, D)
    assert (
        similar(g, "Example Districts Agency", D, [g], org, D + timedelta(days=1))
        is None
    )
    assert similar(g, None, D, [g], org, D) is None
    assert similar(g, "Example Districts Agency", None, [g], org, D) is None
