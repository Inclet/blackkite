"""Date parsing: explicit year required, Kigali local time, end-of-day deadlines."""

from datetime import UTC, datetime

import pytest

from blackkite.pipeline.dates import parse_date, parse_extracted_date


def utc(*a):
    return datetime(*a, tzinfo=UTC)


@pytest.mark.parametrize(
    ("text", "edge", "expected"),
    [
        ("2026-11-30", "start", utc(2026, 11, 29, 22)),
        ("2026-11-30", "end", utc(2026, 11, 30, 21, 59, 59)),
        ("2026-11-30T17:00", "end", utc(2026, 11, 30, 15)),
        ("2026-11-30T17:00:00Z", "end", utc(2026, 11, 30, 17)),
        ("2026-11-30T17:00+03:00", "end", utc(2026, 11, 30, 14)),
        ("Closes 30 Nov 2026, 5pm", "end", utc(2026, 11, 30, 15)),
        ("Deadline: 30th of November, 2026 at 10:00 am", "end", utc(2026, 11, 30, 8)),
        ("November 30, 2026 17h00", "end", utc(2026, 11, 30, 15)),
        ("Tuesday, Dec. 1 2026", "start", utc(2026, 11, 30, 22)),
        ("30/11/2026", "end", utc(2026, 11, 30, 21, 59, 59)),
        ("01.12.26", "start", utc(2026, 11, 30, 22)),
        ("30 Nov 2026 at noon", "end", utc(2026, 11, 30, 10)),
    ],
)
def test_parse_date_with_explicit_year(text, edge, expected):
    r = parse_date(text, edge)
    assert r.status == "ok", text
    assert r.value == expected


@pytest.mark.parametrize(
    "text", ["25 November", "Closes Nov 30th, 5pm", "Monday 1 December"]
)
def test_date_without_a_year_is_not_guessed(text):
    r = parse_date(text)
    assert r.status == "no_year"
    assert r.value is None
    assert r.raw == text


@pytest.mark.parametrize("text", ["soon", "TBC", "31 Feb 2026", "2026-13-01"])
def test_unparseable(text):
    assert parse_date(text).status == "unparsed"


def test_empty():
    assert parse_date(None).status == "empty"
    assert parse_date("  ").status == "empty"


def test_extracted_date_needs_the_year_in_its_snippet():
    ok = parse_extracted_date("2026-11-30", "Bids close on 30 November 2026.", "end")
    assert ok.ok and ok.value == utc(2026, 11, 30, 21, 59, 59)
    # The model supplied a year the text does not state: rejected, raw kept.
    guessed = parse_extracted_date("2026-11-25", "Join us on 25 November!")
    assert guessed.status == "no_year"
    assert guessed.value is None
    assert guessed.raw == "Join us on 25 November!"
    # A year in the snippet that is not the extracted one is not support either.
    wrong = parse_extracted_date("2026-11-25", "25 November 2024 at Norrsken")
    assert wrong.status == "no_year"
    # Two-digit numeric years are stated years.
    assert parse_extracted_date("2026-12-01", "closing 01/12/26").ok


def test_extracted_date_must_match_day_and_month_of_the_snippet():
    # Reviewer's example: the year is right but day and month are not.
    bad = parse_extracted_date("2026-12-30", "Bids close on 30 November 2026.", "end")
    assert bad.status == "mismatch" and bad.value is None
    assert bad.raw == "Bids close on 30 November 2026."
    assert parse_extracted_date("2026-11-03", "30/11/2026").status == "mismatch"
    assert parse_extracted_date("2026-11-30", "Closing 30/11/2026").ok
    assert parse_extracted_date("2026-11-30", "November 30th, 2026").ok
    assert parse_extracted_date("2026-11-30T10:00", "2026-11-30 at 10:00").ok
    # One stated year serving a range.
    assert parse_extracted_date("2026-11-30", "30 November to 2 December 2026").ok
    assert parse_extracted_date("2026-12-02", "30 November to 2 December 2026").ok
    # Day and month right, no year anywhere: still a guessed year.
    assert parse_extracted_date("2026-11-30", "Closes 30 Nov").status == "no_year"
    # No date at all in the snippet.
    assert parse_extracted_date("2026-11-30", "Deadline below").status == "mismatch"
