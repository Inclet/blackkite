"""Date parsing for the validate stage (spec 5 step 6, spec 2.5).

A date counts only when the text states its year. "25 November" is never completed
with a guessed year: it comes back as ``no_year`` so the caller can keep the raw text
and flag the item for review.

Times without a zone are Kigali local time (CAT, UTC+2; Rwanda has no daylight
saving, so a fixed offset is exact). A date with no time is read as the start of the
day, or the end of the day (23:59:59) for deadlines and event ends: "closes 30 Nov"
means the whole of 30 Nov is still open.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Literal

KIGALI = timezone(timedelta(hours=2), "CAT")

DateStatus = Literal["ok", "no_year", "unparsed", "empty", "mismatch"]
DayEdge = Literal["start", "end"]

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_MONTH = r"(?P<month>" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?"
_DAY = r"(?P<day>\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?P<year>\d{4})"

_ISO_RE = re.compile(
    r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"(?:[T ](?P<h>\d{2}):(?P<m>\d{2})(?::(?P<s>\d{2})(?:\.\d+)?)?"
    r"(?P<tz>Z|[+-]\d{2}:?\d{2})?)?",
)
# 30 November 2026, 30th of Nov. 2026, 30 Nov, 2026 ; year optional so we can tell
# "no year" from "no date".
_DMY_RE = re.compile(
    r"\b" + _DAY + r"\s*(?:of\s+)?" + _MONTH + r"(?:,?\s*" + _YEAR + r"\b)?",
    re.IGNORECASE,
)
# November 30, 2026 ; Nov 30th 2026
_MDY_RE = re.compile(
    r"\b" + _MONTH + r"\s+" + _DAY + r"\b(?:,?\s*" + _YEAR + r"\b)?",
    re.IGNORECASE,
)
# 30/11/2026, 30.11.2026, 30-11-26 (day first, the convention in Rwanda)
_NUM_RE = re.compile(
    r"\b(?P<day>\d{1,2})[/.\-](?P<month>\d{1,2})[/.\-](?P<year>\d{4}|\d{2})\b"
)
_TIME_RE = re.compile(
    r"\b(?P<h>\d{1,2})(?:[:.h](?P<m>\d{2}))?\s*(?P<ampm>a\.?m\.?|p\.?m\.?)"
    r"|\b(?P<h24>\d{1,2})[:h](?P<m24>\d{2})\b",
    re.IGNORECASE,
)
_NOON_RE = re.compile(r"\bnoon\b|\bmidday\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


@dataclass(frozen=True, slots=True)
class ParsedDate:
    status: DateStatus
    value: datetime | None = None  # timezone-aware UTC when status == "ok"
    raw: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _time_of(text: str) -> time | None:
    if _NOON_RE.search(text):
        return time(12, 0)
    m = _TIME_RE.search(text)
    if not m:
        return None
    if m.group("h") is not None:
        h = int(m.group("h"))
        minute = int(m.group("m") or 0)
        pm = m.group("ampm").lower().startswith("p")
        if not 1 <= h <= 12 or minute > 59:
            return None
        h = (h % 12) + (12 if pm else 0)
        return time(h, minute)
    h, minute = int(m.group("h24")), int(m.group("m24"))
    if h > 23 or minute > 59:
        return None
    return time(h, minute)


def _combine(d: date, t: time | None, edge: DayEdge) -> datetime:
    if t is None:
        t = time(23, 59, 59) if edge == "end" else time(0, 0)
    return datetime.combine(d, t, tzinfo=KIGALI).astimezone(UTC)


def _search_with_dates(text: str) -> tuple[re.Match[str], str] | None:
    """First date-looking match, trying the forms from most to least specific."""
    for kind, regex in (("iso", _ISO_RE), ("num", _NUM_RE)):
        m = regex.search(text)
        if m:
            return m, kind
    best: tuple[re.Match[str], str] | None = None
    for kind, regex in (("dmy", _DMY_RE), ("mdy", _MDY_RE)):
        m = regex.search(text)
        if m and (best is None or m.start() < best[0].start()):
            best = (m, kind)
    return best


def parse_date(text: str | None, edge: DayEdge = "start") -> ParsedDate:
    """Parse a date as a source wrote it. Never invents a year."""
    if text is None or not text.strip():
        return ParsedDate("empty", raw=text)
    raw = text
    found = _search_with_dates(text)
    if found is None:
        return ParsedDate("unparsed", raw=raw)
    m, kind = found
    if kind == "iso":
        try:
            d = date(int(m["year"]), int(m["month"]), int(m["day"]))
        except ValueError:
            return ParsedDate("unparsed", raw=raw)
        if m["h"] is None:
            return ParsedDate("ok", _combine(d, _time_of(text[m.end() :]), edge), raw)
        t = time(int(m["h"]), int(m["m"]), int(m["s"] or 0))
        tz = KIGALI
        if m["tz"]:
            if m["tz"] == "Z":
                tz = UTC
            else:
                sign = 1 if m["tz"][0] == "+" else -1
                hh, mm = int(m["tz"][1:3]), int(m["tz"][-2:])
                tz = timezone(sign * timedelta(hours=hh, minutes=mm))
        return ParsedDate("ok", datetime.combine(d, t, tzinfo=tz).astimezone(UTC), raw)
    month = MONTHS[m["month"].lower()] if kind in ("dmy", "mdy") else int(m["month"])
    day = int(m["day"])
    if m["year"] is None:
        return ParsedDate("no_year", raw=raw)
    year = int(m["year"])
    if year < 100:
        year += 2000
    try:
        d = date(year, month, day)
    except ValueError:
        return ParsedDate("unparsed", raw=raw)
    rest = text[: m.start()] + " " + text[m.end() :]
    return ParsedDate("ok", _combine(d, _time_of(rest), edge), raw)


def _dates_in(text: str) -> list[tuple[int, int, int | None]]:
    """Every (day, month, year or None) the text states, in any supported form."""
    found: list[tuple[int, int, int | None]] = []
    for kind, regex in (
        ("iso", _ISO_RE),
        ("num", _NUM_RE),
        ("dmy", _DMY_RE),
        ("mdy", _MDY_RE),
    ):
        for m in regex.finditer(text):
            month = (
                MONTHS[m["month"].lower()]
                if kind in ("dmy", "mdy")
                else int(m["month"])
            )
            year = int(m["year"]) if m["year"] else None
            if year is not None and year < 100:
                year += 2000
            found.append((int(m["day"]), month, year))
    return found


def parse_extracted_date(
    value: str | None, snippet: str | None, edge: DayEdge = "start"
) -> ParsedDate:
    """Check a date the LLM returned (ISO 8601) against the snippet it quoted.

    The snippet must state the same day, month and year as the value (Kigali
    calendar date). The year may stand once for several dates ("30 November to
    2 December 2026"). Results:

    * ``ok``: the snippet states that date with its year;
    * ``no_year``: the snippet states the day and month but no year: the model
      supplied the year itself, and that is a guess we do not accept;
    * ``mismatch``: the snippet does not state that day and month at all.
    """
    if not value:
        return ParsedDate("empty", raw=snippet)
    parsed = parse_date(value, edge)
    if not parsed.ok or parsed.value is None:
        return ParsedDate("unparsed", raw=snippet or value)
    raw = snippet or value
    if not snippet:
        return ParsedDate("no_year", raw=raw)
    local = parsed.value.astimezone(KIGALI).date()
    same_day = [
        y for d, m, y in _dates_in(snippet) if (d, m) == (local.day, local.month)
    ]
    if not same_day:
        return ParsedDate("mismatch", raw=raw)
    if local.year in same_day:
        return ParsedDate("ok", parsed.value, raw)
    if None in same_day and any(
        int(y.group(0)) == local.year for y in _YEAR_RE.finditer(snippet)
    ):
        return ParsedDate("ok", parsed.value, raw)
    return ParsedDate("no_year", raw=raw)


def kigali_date(value: datetime) -> date:
    return value.astimezone(KIGALI).date()
