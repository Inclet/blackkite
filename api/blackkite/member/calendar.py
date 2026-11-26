"""Calendar of deadlines and events (spec 8; docs/api-contract.md section 5).

``GET /api/calendar`` lists the caller's visible items with a deadline or an
event date in a window of Kigali calendar days, grouped by day. The rows come
from the feed's own rules (member/feed.py): visibility, mutes, dismissed items
left out, decision 41 (tenders and funding without a fit word hidden unless
the caller tracks them or owns them). Closed items show only when the caller
tracks them (saved, acting, done) or owns them, as with the feed's closed
status filters: an untracked closed item is hard-filtered (spec 7).

Entries per item:

* ``deadline``: on the Kigali day of ``deadline_at`` (any stream; an event's
  registration deadline too);
* events: ``event`` on the first day when the event lasts one Kigali day (or
  has no end), else ``event_start`` on the first day and ``event_end`` on the
  last. Days in between carry no entry.

``time`` is the Kigali time ("HH:MM") when the source stated one. A date stated
without a time is stored as the start of the day (event starts) or its last
second (deadlines and event ends) (pipeline/dates.py), and then has no time.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session

from blackkite.db.models import OPPORTUNITY_STATUSES, Opportunity, User
from blackkite.member import schemas as S
from blackkite.member.feed import KEPT_STATES, FeedFilters, feed_rows
from blackkite.member.view import Row, fit_for
from blackkite.pipeline.dates import KIGALI, kigali_date

MAX_DAYS = 120
KINDS = ("deadlines", "events", "all")
END_OF_DAY = time(23, 59, 59)
START_OF_DAY = time(0, 0)


def day_start(d: date) -> datetime:
    return datetime.combine(d, START_OF_DAY, tzinfo=KIGALI).astimezone(UTC)


def stated_time(value: datetime, edge: str) -> time | None:
    """The Kigali time of a stored date, or None when only the date was stated."""
    t = value.astimezone(KIGALI).time().replace(microsecond=0)
    if edge == "end" and t == END_OF_DAY:
        return None
    if edge == "start" and t == START_OF_DAY:
        return None
    return t


@dataclass(frozen=True, slots=True)
class Mark:
    """One date of one item: the kind and its Kigali day and time."""

    kind: str  # deadline | event_start | event_end | event
    day: date
    at: datetime
    time: time | None


def marks(opp: Opportunity) -> list[Mark]:
    out: list[Mark] = []
    if opp.deadline_at is not None:
        out.append(
            Mark(
                "deadline",
                kigali_date(opp.deadline_at),
                opp.deadline_at,
                stated_time(opp.deadline_at, "end"),
            )
        )
    if opp.stream == "event" and opp.event_start is not None:
        start = kigali_date(opp.event_start)
        start_time = stated_time(opp.event_start, "start")
        end = kigali_date(opp.event_end) if opp.event_end else None
        if end is None or end <= start:
            out.append(Mark("event", start, opp.event_start, start_time))
        else:
            out.append(Mark("event_start", start, opp.event_start, start_time))
            out.append(
                Mark(
                    "event_end",
                    end,
                    opp.event_end,  # type: ignore[arg-type]
                    stated_time(opp.event_end, "end"),  # type: ignore[arg-type]
                )
            )
    return out


def _wanted(mark: Mark, kind: str) -> bool:
    if kind == "deadlines":
        return mark.kind == "deadline"
    if kind == "events":
        return mark.kind != "deadline"
    return True


def _date_clause(first: date, last: date) -> sa.ColumnElement[bool]:
    lo, hi = day_start(first), day_start(last + timedelta(days=1))

    def within(col):
        return sa.and_(col >= lo, col < hi)

    return sa.or_(
        within(Opportunity.deadline_at),
        sa.and_(
            Opportunity.stream == "event",
            sa.or_(within(Opportunity.event_start), within(Opportunity.event_end)),
        ),
    )


def calendar_rows(
    db: Session, user: User, first: date, last: date, now: datetime
) -> list[Row]:
    f = FeedFilters(statuses=OPPORTUNITY_STATUSES)
    return feed_rows(db, user, f, now, where=_date_clause(first, last), limit=None)


def _entry(row: Row, mark: Mark, now: datetime) -> S.CalendarEntry:
    o = row.opp
    return S.CalendarEntry(
        id=str(o.id),
        stream=o.stream,
        title=o.title,
        organisation_short=o.organisation_short,
        kind=mark.kind,
        time=mark.time.strftime("%H:%M") if mark.time else None,
        fit=fit_for(row, now),
        state=row.state,
        provisional=bool(row.best and row.best.provisional),
    )


def calendar(
    db: Session,
    user: User,
    first: date,
    last: date,
    now: datetime,
    *,
    kind: str = "all",
    saved: bool = False,
) -> S.CalendarOut:
    by_day: dict[date, list[tuple[tuple, S.CalendarEntry]]] = defaultdict(list)
    for row in calendar_rows(db, user, first, last, now):
        if saved and row.state not in KEPT_STATES:
            continue
        for mark in marks(row.opp):
            if not (first <= mark.day <= last) or not _wanted(mark, kind):
                continue
            # All-day entries first, then by time, then title.
            key = (
                mark.time is not None,
                mark.time or START_OF_DAY,
                row.opp.title,
                str(row.opp.id),
                mark.kind,
            )
            by_day[mark.day].append((key, _entry(row, mark, now)))
    return S.CalendarOut(
        days=[
            S.CalendarDay(
                date=d.isoformat(),
                entries=[e for _, e in sorted(by_day[d], key=lambda x: x[0])],
            )
            for d in sorted(by_day)
        ]
    )
