"""Private manual items (spec 6; docs/api-contract.md section 5).

A member adds what no source carries (a WhatsApp group's tender, a notice
board, a word-of-mouth deal): ``visibility = private``, ``owner_user_id`` = the
caller, ``verification = unverified``. Nobody else ever sees it (spec 10):
every lookup here is by (id, owner = caller, private), so another user's item,
admins included, is "not found".

Dates follow the pipeline's rules (pipeline/dates.py, pipeline/validate.py):
the text must state its year ("30 Nov 2026", "2026-11-30", "30/11/2026 17:00"),
never guessed, and lie in the plausible window (a year back to two years
ahead). A date without a time is the end of the day for deadlines and event
ends, the start for event starts; times without a zone are Kigali time. Only
events take event dates.

Creating or editing queues scoring for the owner only (worker/item_scores.py);
nothing is scored in the request. The ``notes`` field is the owner's own note
on the item (``user_opportunity.note``), as on any other item. Deleting the
item removes the owner's per-user rows with it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import urlsplit

import sqlalchemy as sa
from pydantic import Field, StringConstraints
from sqlalchemy.orm import Session

from blackkite.collectors.problems import Problem
from blackkite.db.models import (
    AlertLog,
    ChangeEvent,
    Opportunity,
    User,
    UserOpportunity,
    UserOpportunityScore,
)
from blackkite.member.schemas import CamelIn, Stream
from blackkite.pipeline.dates import parse_date
from blackkite.pipeline.validate import check_date, status_for

Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
DateText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]

# Request field -> (column, day edge for a date with no time).
DATE_FIELDS = {
    "deadline": ("deadline_at", "end"),
    "event_start": ("event_start", "start"),
    "event_end": ("event_end", "end"),
}
# Request field -> column, for plain values.
PLAIN_FIELDS = {
    "stream": "stream",
    "title": "title",
    "organisation": "organisation",
    "value": "value_amount",
    "currency": "value_currency",
    "location": "location",
    "url": "manual_url",
}
DATE_MESSAGES = {
    "no_year": "include the year, for example 30 Nov 2026",
    "unparsed": "is not a date we understand; write it like 30 Nov 2026",
    "empty": "is not a date we understand; write it like 30 Nov 2026",
    "out_of_window": "must be between a year ago and two years from now",
}


class ItemIn(CamelIn):
    stream: Stream
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ]
    organisation: Text | None = None
    deadline: DateText | None = None
    event_start: DateText | None = None
    event_end: DateText | None = None
    value: Annotated[Decimal, Field(ge=0, lt=Decimal("1e18"))] | None = None
    currency: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True, to_upper=True, pattern="^[A-Za-z]{3}$"
            ),
        ]
        | None
    ) = None
    location: Text | None = None
    url: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None
    ) = None
    notes: Annotated[str, Field(max_length=5000)] | None = None


class ItemPatch(ItemIn):
    """Any field of ``ItemIn``; a field sent as null clears it (``stream`` and
    ``title`` cannot be cleared)."""

    stream: Stream | None = None  # type: ignore[assignment]
    title: (
        Annotated[  # type: ignore[assignment]
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
        ]
        | None
    ) = None


class ItemInvalid(Exception):
    def __init__(self, problems: list[Problem]) -> None:
        self.problems = problems
        super().__init__(problems)


def _url_problem(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return "must be a web address starting with http:// or https://"
    if any(c.isspace() or ord(c) < 0x20 or ord(c) == 0x7F for c in url):
        return "must not contain spaces"
    if parts.username or parts.password:
        return "must not contain a user name or password"
    return None


def _parse_dates(
    body: dict[str, Any], now: datetime, problems: list[Problem]
) -> dict[str, datetime | None]:
    out: dict[str, datetime | None] = {}
    for name, (column, edge) in DATE_FIELDS.items():
        if name not in body:
            continue
        text = body[name]
        if text is None or not str(text).strip():
            out[column] = None
            continue
        check = check_date(column, parse_date(text, edge), now)  # type: ignore[arg-type]
        if check.status != "ok":
            problems.append(
                Problem((name,), DATE_MESSAGES.get(check.status, "is not valid"))
            )
            continue
        out[column] = check.value
    return out


def _values(
    body: dict[str, Any], current: Opportunity | None, now: datetime
) -> dict[str, Any]:
    """Columns to write, checked as a whole (the stored values fill in what the
    body leaves out). Raises ItemInvalid."""
    problems: list[Problem] = []
    values: dict[str, Any] = {}
    for name, column in PLAIN_FIELDS.items():
        if name in body:
            if name in ("stream", "title") and body[name] is None:
                problems.append(Problem((name,), "cannot be cleared"))
                continue
            values[column] = body[name]
    url = values.get("manual_url")
    if url and (msg := _url_problem(url)):
        problems.append(Problem(("url",), msg))
    values.update(_parse_dates(body, now, problems))

    def final(column: str) -> Any:
        if column in values:
            return values[column]
        return getattr(current, column) if current is not None else None

    stream = final("stream")
    start, end = final("event_start"), final("event_end")
    if stream != "event":
        for name, column in (
            ("event_start", "event_start"),
            ("event_end", "event_end"),
        ):
            if final(column) is not None and not any(
                p.path == (name,) for p in problems
            ):
                problems.append(Problem((name,), "only events have event dates"))
    elif end is not None and start is None:
        problems.append(
            Problem(("event_start",), "is needed when there is an event end")
        )
    elif start is not None and end is not None and end < start:
        problems.append(Problem(("event_end",), "is before the event start"))
    if problems:
        raise ItemInvalid(problems)
    return values


def own_item(db: Session, user: User, item_id: uuid.UUID) -> Opportunity | None:
    """The caller's own private item, else None (routes answer 404)."""
    return db.scalar(
        sa.select(Opportunity).where(
            Opportunity.id == item_id,
            Opportunity.visibility == "private",
            Opportunity.owner_user_id == user.id,
        )
    )


def _set_note(db: Session, user: User, opp: Opportunity, notes: str | None) -> None:
    uo = db.scalar(
        sa.select(UserOpportunity).where(
            UserOpportunity.user_id == user.id,
            UserOpportunity.opportunity_id == opp.id,
        )
    )
    if uo is None:
        uo = UserOpportunity(user_id=user.id, opportunity_id=opp.id, state="unseen")
        db.add(uo)
    uo.note = (notes or "").strip() or None


def _refresh_status(opp: Opportunity, now: datetime) -> None:
    opp.status = status_for(
        "open" if opp.status == "expired" else opp.status,
        opp.stream,
        opp.deadline_at,
        opp.event_start,
        opp.event_end,
        now,
    )


def request_scoring(opp: Opportunity, now: datetime) -> None:
    """Queue the item for the worker (worker/item_scores.py)."""
    opp.score_requested_at = now


def create_item(db: Session, user: User, body: ItemIn, now: datetime) -> Opportunity:
    data = body.model_dump()
    values = _values(data, None, now)
    opp = Opportunity(
        **values,
        visibility="private",
        owner_user_id=user.id,
        verification="unverified",
        needs_review=False,
        evidence={"_trust": "unconfirmed"},
        status="open",
    )
    _refresh_status(opp, now)
    request_scoring(opp, now)
    db.add(opp)
    db.flush()
    if body.notes is not None:
        _set_note(db, user, opp, body.notes)
    db.flush()
    return opp


def _json(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return v


def update_item(
    db: Session, user: User, opp: Opportunity, body: ItemPatch, now: datetime
) -> Opportunity:
    data = body.model_dump(include=body.model_fields_set)
    values = _values(data, opp, now)
    changed = False
    for column, new in values.items():
        old = getattr(opp, column)
        if column == "value_amount" and old is not None and new is not None:
            same = Decimal(old) == Decimal(new)
        else:
            same = old == new
        if same:
            continue
        db.add(
            ChangeEvent(
                opportunity_id=opp.id,
                field=column,
                old=_json(old),
                new=_json(new),
                at=now,
            )
        )
        setattr(opp, column, new)
        changed = True
    if changed:
        _refresh_status(opp, now)
        request_scoring(opp, now)
    if "notes" in data:
        _set_note(db, user, opp, data["notes"])
    db.flush()
    return opp


def delete_item(db: Session, user: User, opp: Opportunity) -> None:
    """Delete the item and the owner's per-user rows on it."""
    for table in (UserOpportunity, UserOpportunityScore, AlertLog):
        db.execute(
            sa.delete(table).where(
                table.user_id == user.id, table.opportunity_id == opp.id
            )
        )
    db.execute(
        sa.delete(Opportunity).where(
            Opportunity.id == opp.id,
            Opportunity.owner_user_id == user.id,
            Opportunity.visibility == "private",
        )
    )
    db.flush()
