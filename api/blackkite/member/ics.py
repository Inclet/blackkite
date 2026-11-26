"""The personal calendar feed as iCalendar (RFC 5545).

What goes in: the caller's saved and acting items they can still see (the
shortlist's rule: member visibility; no fit rule, decision 41 keeps saved items),
one VEVENT per deadline ("Closes: {title}") and one per event ("{title}", from
its first to its last day). Each VEVENT carries only the title, the
organisation, the dates and the app link (DESCRIPTION and URL): never notes,
scores, reasons or profiles.

Dates: a date stated with a time is a DATE-TIME with ``TZID=Africa/Kigali``
(the VTIMEZONE is included: CAT, UTC+2 all year, no daylight saving); a date
stated without one is an all-day DATE (DTEND the day after, exclusive). A
deadline with a time has no DTEND (RFC 5545 3.6.1: it ends when it starts).

UIDs are stable per item and kind (``{id}-deadline@blackkite``,
``{id}-event@blackkite``) so calendar apps update entries in place. DTSTAMP is
the last change to the item or the caller's state, in UTC.

Text values are escaped (backslash, semicolon, comma, newlines; other control
characters dropped) and every content line is folded at 75 octets without
splitting a UTF-8 character; lines end with CRLF.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session

from blackkite.db.models import Opportunity, User, UserOpportunity
from blackkite.member.calendar import stated_time
from blackkite.member.view import SHORTLIST_STATES, member_visible
from blackkite.pipeline.dates import KIGALI, kigali_date

TZID = "Africa/Kigali"
PRODID = "-//Blackkite//Calendar feed//EN"
CRLF = "\r\n"
_CTL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

VTIMEZONE = (
    "BEGIN:VTIMEZONE",
    f"TZID:{TZID}",
    "BEGIN:STANDARD",
    "DTSTART:19700101T000000",
    "TZOFFSETFROM:+0200",
    "TZOFFSETTO:+0200",
    "TZNAME:CAT",
    "END:STANDARD",
    "END:VTIMEZONE",
)


def escape_text(value: str) -> str:
    """A TEXT value (RFC 5545 3.3.11)."""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = _CTL.sub("", value.replace("\t", " "))
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def fold(line: str) -> str:
    """Fold one content line at 75 octets (RFC 5545 3.1); continuation lines
    start with a space, which counts toward their 75."""
    out: list[str] = []
    current = ""
    size = 0
    limit = 75
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > limit:
            out.append(current)
            current, size, limit = " ", 1, 75
        current += ch
        size += n
    out.append(current)
    return CRLF.join(out)


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _local(value: datetime) -> str:
    return value.astimezone(KIGALI).strftime("%Y%m%dT%H%M%S")


def _day(value: date) -> str:
    return value.strftime("%Y%m%d")


def _app_link(web_base_url: str, opp: Opportunity) -> str:
    return f"{web_base_url.rstrip('/')}/o/{opp.id}"


def _vevent(
    opp: Opportunity,
    kind: str,
    summary: str,
    times: list[str],
    stamp: datetime,
    web_base_url: str,
) -> list[str]:
    link = _app_link(web_base_url, opp)
    description = "\n".join(p for p in ((opp.organisation or "").strip(), link) if p)
    return [
        "BEGIN:VEVENT",
        f"UID:{opp.id}-{kind}@blackkite",
        f"DTSTAMP:{_utc(stamp)}",
        *times,
        f"SUMMARY:{escape_text(summary)}",
        f"DESCRIPTION:{escape_text(description)}",
        f"URL:{link}",
        "TRANSP:TRANSPARENT",
        "END:VEVENT",
    ]


def _deadline_times(deadline: datetime) -> list[str]:
    if stated_time(deadline, "end") is not None:
        return [f"DTSTART;TZID={TZID}:{_local(deadline)}"]
    d = kigali_date(deadline)
    return [
        f"DTSTART;VALUE=DATE:{_day(d)}",
        f"DTEND;VALUE=DATE:{_day(d + timedelta(days=1))}",
    ]


def _event_times(start: datetime, end: datetime | None) -> list[str]:
    start_timed = stated_time(start, "start") is not None
    end_timed = end is not None and stated_time(end, "end") is not None
    if start_timed and end is None:
        return [f"DTSTART;TZID={TZID}:{_local(start)}"]
    if start_timed and end_timed and end > start:  # type: ignore[operator]
        return [
            f"DTSTART;TZID={TZID}:{_local(start)}",
            f"DTEND;TZID={TZID}:{_local(end)}",  # type: ignore[arg-type]
        ]
    first = kigali_date(start)
    last = max(first, kigali_date(end)) if end is not None else first
    return [
        f"DTSTART;VALUE=DATE:{_day(first)}",
        f"DTEND;VALUE=DATE:{_day(last + timedelta(days=1))}",
    ]


def feed_rows(db: Session, user: User) -> list[tuple[Opportunity, UserOpportunity]]:
    return list(
        db.execute(  # type: ignore[arg-type]
            sa.select(Opportunity, UserOpportunity)
            .join(
                UserOpportunity,
                sa.and_(
                    UserOpportunity.opportunity_id == Opportunity.id,
                    UserOpportunity.user_id == user.id,
                ),
            )
            .where(
                member_visible(user.id),
                UserOpportunity.state.in_(SHORTLIST_STATES),
            )
            .order_by(Opportunity.id)
        ).all()
    )


def events(
    rows: Iterable[tuple[Opportunity, UserOpportunity]], web_base_url: str
) -> list[list[str]]:
    out: list[list[str]] = []
    for opp, uo in rows:
        stamp = max(opp.updated_at, uo.updated_at)
        if opp.deadline_at is not None:
            out.append(
                _vevent(
                    opp,
                    "deadline",
                    f"Closes: {opp.title}",
                    _deadline_times(opp.deadline_at),
                    stamp,
                    web_base_url,
                )
            )
        if opp.stream == "event" and opp.event_start is not None:
            out.append(
                _vevent(
                    opp,
                    "event",
                    opp.title,
                    _event_times(opp.event_start, opp.event_end),
                    stamp,
                    web_base_url,
                )
            )
    return out


def render(db: Session, user: User, web_base_url: str) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Blackkite",
        f"X-WR-TIMEZONE:{TZID}",
        *VTIMEZONE,
    ]
    for ev in events(feed_rows(db, user), web_base_url):
        lines.extend(ev)
    lines.append("END:VCALENDAR")
    return "".join(fold(line) + CRLF for line in lines)
