"""Stage 2: canonical URL and text cleanup."""

import uuid
from datetime import UTC, datetime

import pytest

from blackkite.collectors.base import RawItem
from blackkite.pipeline.normalise import (
    canonical_url,
    clean_organisation,
    clean_title,
    normalise,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("HTTPS://Example.ORG/Tenders/123/", "https://example.org/Tenders/123"),
        ("https://example.org", "https://example.org/"),
        ("https://example.org/", "https://example.org/"),
        ("https://example.org:443/a", "https://example.org/a"),
        ("http://example.org:8080/a", "http://example.org:8080/a"),
        ("https://example.org/a#section-2", "https://example.org/a"),
        (
            "https://example.org/a?utm_source=x&id=7&fbclid=abc&UTM_Medium=y",
            "https://example.org/a?id=7",
        ),
        ("https://example.org/a?b=2&a=1", "https://example.org/a?a=1&b=2"),
        ("https://example.org/a?gclid=1&mc_cid=2", "https://example.org/a"),
        ("https://user:pw@example.org/a", "https://example.org/a"),
        ("https://example.org//a//b/", "https://example.org/a/b"),
    ],
)
def test_canonical_url(url, expected):
    assert canonical_url(url) == expected


def test_canonical_url_is_idempotent():
    u = canonical_url("https://Example.org/x/?utm_campaign=1&q=a b#top")
    assert canonical_url(u) == u


def test_clean_title_unescapes_and_collapses_but_keeps_case():
    assert (
        clean_title("  Supply of  <b>COLD&nbsp;Chain</b>\n Trucks &amp;amp; Vans ")
        == "Supply of COLD Chain Trucks & Vans"
    )


def test_clean_organisation_strips_labels_and_separators():
    assert clean_organisation("Organisation: Example Agency Ltd - ") == (
        "Example Agency Ltd"
    )
    assert clean_organisation(" | ") is None
    assert clean_organisation(None) is None


def test_normalise_builds_raw_text_and_drops_redundant_detail_url():
    sid = uuid.uuid4()
    now = datetime(2026, 11, 25, 8, tzinfo=UTC)
    item = RawItem(
        source_id=sid,
        url="https://Example.org/t/1/?utm_source=feed",
        detail_url="https://example.org/t/1",
        title="Invitation&nbsp;for Bids",
        organisation="By: Example Agency",
        listed_deadline="Closes 30 Nov 2026",
        snippet="Supply of   fuel",
        fetched_at=now,
    )
    n = normalise(item)
    assert n.url == "https://example.org/t/1"
    assert n.detail_url is None
    assert n.title == "Invitation for Bids"
    assert n.organisation == "Example Agency"
    assert n.fetched_at == now and n.source_id == sid
    assert n.raw_text.splitlines() == [
        "Invitation for Bids",
        "Organisation: Example Agency",
        "Deadline: Closes 30 Nov 2026",
        "Supply of fuel",
    ]
