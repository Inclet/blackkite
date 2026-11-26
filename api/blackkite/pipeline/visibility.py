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
* A private manual item an admin made public with its owner's consent
  (``made_public_at`` set) is seen by every member, though no source carries
  it (``published_manual``).
* An **admin** sees every public opportunity, including testing-only ones, plus
  their own private items; never other users' private items (spec 10).

A public item with no source row at all is hidden from members too (nothing
carries it). When listing the sources that carried an item (spec 4.4) to a member,
show only those passing ``visible_source_link()``.

Verification (spec 6) follows the same rule: it is computed only from carrying
sources a member can see (``refresh_verification``), so a testing or retired
original never makes an item "confirmed at the source" to members. It is
recomputed when a source's status or kind changes.

This is the single visibility rule; ``MEMBER_VISIBLE_SOURCE_STATUSES`` is the one
line to change if the owner decides retired sources should keep their items
visible (open question).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from blackkite.db.models import Opportunity, OpportunitySource, Source
from blackkite.pipeline.validate import trust_state, verification_for

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


def published_manual() -> ColumnElement[bool]:
    """A member's manual item an admin made public (spec 6)."""
    return sa.and_(
        Opportunity.visibility == "public", Opportunity.made_public_at.is_not(None)
    )


def member_visible_public() -> ColumnElement[bool]:
    """WHERE clause on ``Opportunity``: a public item members may see."""
    return sa.and_(
        Opportunity.visibility == "public",
        sa.or_(carried_by_visible_source(), published_manual()),
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
    public = Opportunity.visibility == "public" if is_admin else member_visible_public()
    return sa.or_(public, own_private(user_id))


def verification_of(session: Session, opportunity_id: uuid.UUID) -> str:
    """``verification`` from the carrying sources members can see. A link counts
    as original only while its source's kind is still ``original``."""
    rows = session.execute(
        sa.select(OpportunitySource.is_original, Source.kind)
        .join(Source, Source.id == OpportunitySource.source_id)
        .where(
            OpportunitySource.opportunity_id == opportunity_id,
            Source.status.in_(MEMBER_VISIBLE_SOURCE_STATUSES),
        )
    ).all()
    return verification_for((bool(o) and k == "original", k) for o, k in rows)


def refresh_verification(session: Session, opps: Iterable[Opportunity]) -> int:
    """Recompute ``verification`` and ``evidence["_trust"]``. Returns how many
    items changed."""
    changed = 0
    for opp in opps:
        verification = verification_of(session, opp.id)
        ev = dict(opp.evidence or {})
        trust = trust_state(verification, ev)
        if verification != opp.verification or ev.get("_trust") != trust:
            changed += 1
            opp.verification = verification
            ev["_trust"] = trust
            opp.evidence = ev
    return changed


def refresh_verification_for_source(session: Session, source_id: uuid.UUID) -> int:
    """Recompute verification for every item this source carries (call after a
    status or kind change)."""
    opps = session.scalars(
        sa.select(Opportunity).where(
            Opportunity.id.in_(
                sa.select(OpportunitySource.opportunity_id).where(
                    OpportunitySource.source_id == source_id
                )
            )
        )
    ).all()
    n = refresh_verification(session, opps)
    session.flush()
    return n
