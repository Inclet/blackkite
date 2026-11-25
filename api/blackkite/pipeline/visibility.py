"""Who may see a catalogue item. Derived at query time; no column stores it.

Rule (spec 4.3 step 3: a ``testing`` source's items "are stored but hidden from
members"):

* A **member** sees a public opportunity only while at least one source carrying it
  has status ``active`` or ``paused``. Items carried only by ``testing`` (or
  ``suggested``) sources stay hidden, and become visible the moment one of their
  sources is promoted to ``active``; no rewrite of the rows is needed. Pausing a
  source does not hide what it already found. A source that is ``retired`` no
  longer counts (so a testing source that is retired without ever being promoted
  never leaks its items).
* A member sees a private opportunity only if they own it (spec 6).
* An **admin** sees every public opportunity, including testing-only ones, plus
  their own private items; never other users' private items (spec 10).

A public item with no source row at all is hidden from members too (nothing
carries it). When listing the sources that carried an item (spec 4.4) to a member,
show only those passing ``visible_source_link()``.

This is the single visibility rule; ``MEMBER_VISIBLE_SOURCE_STATUSES`` is the one
line to change if the owner decides retired sources should keep their items
visible (open question).
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.sql.elements import ColumnElement

from blackkite.db.models import Opportunity, OpportunitySource, Source

MEMBER_VISIBLE_SOURCE_STATUSES = ("active", "paused")


def carried_by_visible_source() -> ColumnElement[bool]:
    return sa.exists(
        sa.select(sa.literal(1))
        .select_from(OpportunitySource)
        .join(Source, Source.id == OpportunitySource.source_id)
        .where(
            OpportunitySource.opportunity_id == Opportunity.id,
            Source.status.in_(MEMBER_VISIBLE_SOURCE_STATUSES),
        )
    )


def visible_source_link() -> ColumnElement[bool]:
    """WHERE clause on ``Source`` (joined to opportunity_source): the carrying sources
    a member may see listed on an opportunity."""
    return Source.status.in_(MEMBER_VISIBLE_SOURCE_STATUSES)


def own_private(user_id: uuid.UUID) -> ColumnElement[bool]:
    return sa.and_(
        Opportunity.visibility == "private", Opportunity.owner_user_id == user_id
    )


def visible_to(user_id: uuid.UUID, *, is_admin: bool) -> ColumnElement[bool]:
    """WHERE clause on ``Opportunity`` for what this caller may see."""
    public = Opportunity.visibility == "public"
    if not is_admin:
        public = sa.and_(public, carried_by_visible_source())
    return sa.or_(public, own_private(user_id))
