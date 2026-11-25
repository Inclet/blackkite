"""Stage 6, validate: date windows, status, deadline conflicts, trust state.

Plausible windows (relative to the time of the run):

* ``published_at``: from 18 months ago (548 days) to 1 day ahead;
* ``deadline_at``, ``event_start``, ``event_end``: from 1 year ago to 2 years ahead.

A date outside its window, or without an explicit year, or unparseable, is stored
as null; the raw text stays in evidence and the item is flagged ``needs_review``.

Status: deadline passed -> ``expired``; deadline within 7 days -> ``closing_soon``;
otherwise ``open``. Events with no deadline use ``event_end`` (else ``event_start``)
as the moment that ends them. ``awarded`` and ``cancelled`` are never changed here.

Deadline conflicts: each source's deadline is kept in ``evidence["_sources"]``.
When sources give different days (Kigali calendar date), the original source's
deadline wins, else the earliest; ``needs_review`` is set and
``evidence["_deadline_conflict"]`` is true.

Verification and trust (spec 6, spec 12):

* ``verified_original``: an ``original`` source carries the item;
* ``aggregator_only``: every source that carries it is an ``aggregator``;
* ``unverified``: otherwise (publisher, news, community, no original).

UI trust state, stored in ``evidence["_trust"]`` and given by ``trust_state()``:

* ``disagree`` ("sources disagree"): the sources' deadlines conflicted;
* ``confirmed`` ("confirmed at the source"): verified_original and no conflict;
* ``not_confirmed`` ("not yet confirmed"): everything else, including every
  aggregator_only item (spec 10: never present one as confirmed).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from blackkite.pipeline.dates import ParsedDate, kigali_date

PUBLISHED_PAST = timedelta(days=548)
PUBLISHED_FUTURE = timedelta(days=1)
EVENT_PAST = timedelta(days=365)
EVENT_FUTURE = timedelta(days=730)
CLOSING_SOON = timedelta(days=7)

TrustState = Literal["confirmed", "not_confirmed", "disagree"]
FINAL_STATUSES = ("awarded", "cancelled")


def window(field: str, now: datetime) -> tuple[datetime, datetime]:
    if field == "published_at":
        return now - PUBLISHED_PAST, now + PUBLISHED_FUTURE
    return now - EVENT_PAST, now + EVENT_FUTURE


@dataclass(frozen=True, slots=True)
class DateCheck:
    value: datetime | None
    status: str  # ok | no_year | unparsed | empty | out_of_window
    raw: str | None

    @property
    def reviewable(self) -> bool:
        return self.status in ("no_year", "unparsed", "out_of_window")


def check_date(field: str, parsed: ParsedDate, now: datetime) -> DateCheck:
    if not parsed.ok or parsed.value is None:
        return DateCheck(None, parsed.status, parsed.raw)
    lo, hi = window(field, now)
    if not lo <= parsed.value <= hi:
        return DateCheck(None, "out_of_window", parsed.raw)
    return DateCheck(parsed.value, "ok", parsed.raw)


def review_reason(field: str, check: DateCheck) -> str:
    raw = f" ({check.raw!r})" if check.raw else ""
    return {
        "no_year": f"{field}: date has no year{raw}; not guessed",
        "unparsed": f"{field}: date not understood{raw}",
        "out_of_window": f"{field}: date outside the plausible window{raw}",
    }[check.status]


def status_for(
    current: str,
    stream: str,
    deadline_at: datetime | None,
    event_start: datetime | None,
    event_end: datetime | None,
    now: datetime,
) -> str:
    if current in FINAL_STATUSES:
        return current
    end = deadline_at
    if end is None and stream == "event":
        end = event_end or event_start
    if end is None:
        return "open"
    if end < now:
        return "expired"
    if end - now <= CLOSING_SOON:
        return "closing_soon"
    return "open"


@dataclass(frozen=True, slots=True)
class SourceDeadline:
    source_id: str
    is_original: bool
    value: datetime


def resolve_deadline(
    candidates: Iterable[SourceDeadline],
) -> tuple[datetime | None, bool, str | None]:
    """(chosen deadline, conflict?, rule used). Days compared on the Kigali calendar."""
    items = list(candidates)
    if not items:
        return None, False, None
    days = {kigali_date(c.value) for c in items}
    conflict = len(days) > 1
    originals = [c for c in items if c.is_original]
    if originals:
        # Latest-stated time on the original's day; several original rows are one notice.
        return max(c.value for c in originals), conflict, "original"
    if not conflict:
        return max(c.value for c in items), False, "agreed"
    return min(c.value for c in items), True, "earliest"


def verification_for(links: Iterable[tuple[bool, str]]) -> str:
    """``links``: (is_original, source kind) for every source carrying the item."""
    rows = list(links)
    if any(is_original or kind == "original" for is_original, kind in rows):
        return "verified_original"
    if rows and all(kind == "aggregator" for _, kind in rows):
        return "aggregator_only"
    return "unverified"


def trust_state(verification: str, evidence: dict[str, Any] | None) -> TrustState:
    if evidence and evidence.get("_deadline_conflict"):
        return "disagree"
    if verification == "verified_original":
        return "confirmed"
    return "not_confirmed"
