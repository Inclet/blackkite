"""Admin bare catalogue (spec 11 M1) and the needs_review queue (spec 3).

Lists every public item, including those carried only by testing sources (which
members do not see; ``memberVisible`` says which). Private items are never listed
here (spec 10: admins manage sources and users, not other users' items), with
one exception: ``?shareable=true`` lists private manual items whose owner has
allowed an admin to make them public (spec 6), and only those; nothing names
the owner or carries their notes, state or scores. ``POST /{id}/publish`` makes
one public, only while that consent is on (409 otherwise), and records who and
when in change_event; the owner stays on the item for attribution only, and the
worker then scores it for everyone (worker/item_scores.py).
Reviewing an item clears ``needs_review`` and ``evidence["_review"]`` together and
records the cleared reasons in change_event.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from blackkite.auth.deps import AdminUser, DbDep, require_admin
from blackkite.db.models import ChangeEvent, Opportunity, OpportunitySource, Source
from blackkite.member.schemas import CamelModel, Stream
from blackkite.pipeline.dates import kigali_date
from blackkite.pipeline.validate import trust_state
from blackkite.pipeline.visibility import member_visible_public

router = APIRouter(prefix="/admin/catalogue", dependencies=[Depends(require_admin)])


class ReviewReason(CamelModel):
    code: str
    detail: str


class CatalogueSource(CamelModel):
    name: str
    status: str
    kind: str
    is_original: bool
    url: str


class CatalogueItem(CamelModel):
    omit_if_none = frozenset({"share_consent_at", "made_public_at", "url"})

    id: uuid.UUID
    stream: str
    title: str
    organisation: str | None
    status: str
    verification: str
    trust: str
    needs_review: bool
    review_reasons: list[ReviewReason]
    deadline: str | None
    member_visible: bool
    sources: list[CatalogueSource]
    # "private" only in the shareable list.
    visibility: str = "public"
    # Manual items (spec 6): when the owner allowed sharing, when it was made
    # public, and the link the owner gave. Left out when null (collected items).
    share_consent_at: datetime | None = None
    made_public_at: datetime | None = None
    url: str | None = None
    created_at: datetime
    updated_at: datetime


class CataloguePage(CamelModel):
    total: int
    items: list[CatalogueItem]


def _reasons(ev: dict[str, Any]) -> list[ReviewReason]:
    out = []
    for r in ev.get("_review") or []:
        if isinstance(r, dict):
            out.append(
                ReviewReason(
                    code=str(r.get("code", "")), detail=str(r.get("detail", ""))
                )
            )
    return out


def _items(db: Session, rows: list[tuple[Opportunity, bool]]) -> list[CatalogueItem]:
    ids = [o.id for o, _ in rows]
    links: dict[uuid.UUID, list[CatalogueSource]] = defaultdict(list)
    if ids:
        for link, src in db.execute(
            sa.select(OpportunitySource, Source)
            .join(Source, Source.id == OpportunitySource.source_id)
            .where(OpportunitySource.opportunity_id.in_(ids))
            .order_by(OpportunitySource.first_seen)
        ).all():
            links[link.opportunity_id].append(
                CatalogueSource(
                    name=src.name,
                    status=src.status,
                    kind=src.kind,
                    is_original=link.is_original,
                    url=link.url,
                )
            )
    out = []
    for o, visible in rows:
        ev = o.evidence or {}
        out.append(
            CatalogueItem(
                id=o.id,
                stream=o.stream,
                title=o.title,
                organisation=o.organisation,
                status=o.status,
                verification=o.verification,
                trust=ev.get("_trust") or trust_state(o.verification, ev),
                needs_review=o.needs_review,
                review_reasons=_reasons(ev),
                deadline=kigali_date(o.deadline_at).isoformat()
                if o.deadline_at
                else None,
                member_visible=visible,
                sources=links.get(o.id, []),
                visibility=o.visibility,
                share_consent_at=o.share_consent_at,
                made_public_at=o.made_public_at,
                url=o.manual_url,
                created_at=o.created_at,
                updated_at=o.updated_at,
            )
        )
    return out


@router.get("", response_model=CataloguePage)
def list_catalogue(
    db: DbDep,
    needs_review: Annotated[bool | None, Query(alias="needsReview")] = None,
    stream: Stream | None = None,
    shareable: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CataloguePage:
    where: list[Any] = (
        [Opportunity.visibility == "private", Opportunity.share_consent_at.is_not(None)]
        if shareable
        else [Opportunity.visibility == "public"]
    )
    if needs_review is not None:
        where.append(Opportunity.needs_review.is_(needs_review))
    if stream:
        where.append(Opportunity.stream == stream)
    total = db.scalar(sa.select(sa.func.count()).select_from(Opportunity).where(*where))
    rows = db.execute(
        sa.select(Opportunity, member_visible_public())
        .where(*where)
        .order_by(
            Opportunity.needs_review.desc(),
            Opportunity.created_at.desc(),
            Opportunity.id,
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return CataloguePage(
        total=total or 0, items=_items(db, [(o, bool(v)) for o, v in rows])
    )


@router.post("/{opportunity_id}/review", response_model=CatalogueItem)
def mark_reviewed(
    opportunity_id: uuid.UUID, admin: AdminUser, db: DbDep
) -> CatalogueItem:
    opp = db.scalar(
        sa.select(Opportunity).where(
            Opportunity.id == opportunity_id, Opportunity.visibility == "public"
        )
    )
    if opp is None:
        raise HTTPException(404, "Opportunity not found")
    ev = dict(opp.evidence or {})
    cleared = ev.pop("_review", None) or []
    if opp.needs_review or cleared:
        db.add(
            ChangeEvent(
                opportunity_id=opp.id,
                field="needs_review",
                old={"needs_review": opp.needs_review, "reasons": cleared},
                new={"needs_review": False, "reviewed_by": str(admin.id)},
                at=datetime.now(UTC),
            )
        )
        opp.needs_review = False
        opp.evidence = ev
        db.commit()
        db.refresh(opp)
    visible = bool(
        db.scalar(sa.select(member_visible_public()).where(Opportunity.id == opp.id))
    )
    return _items(db, [(opp, visible)])[0]


NO_CONSENT = "The owner has not agreed to share this item, so it stays private."
NOT_MANUAL = "Only a member's own item can be made public this way."


@router.post("/{opportunity_id}/publish", response_model=CatalogueItem)
def publish(opportunity_id: uuid.UUID, admin: AdminUser, db: DbDep) -> CatalogueItem:
    # Row lock first, clock after: an owner's edit that committed before us is
    # dated before made_public_at, so it stays in the private history that only
    # the owner sees (member/view.py private_history_hidden); one that waits on
    # the lock finds the item public and is refused (member/items.py).
    opp = db.scalar(
        sa.select(Opportunity).where(Opportunity.id == opportunity_id).with_for_update()
    )
    if opp is None:
        raise HTTPException(404, "Opportunity not found")
    if opp.visibility == "public" and opp.made_public_at is None:
        raise HTTPException(409, NOT_MANUAL)
    if opp.made_public_at is None:
        if opp.share_consent_at is None:
            raise HTTPException(409, NO_CONSENT)
        now = datetime.now(UTC)
        # Guarded so a consent withdrawn a moment ago is never overridden.
        done = db.execute(
            sa.update(Opportunity)
            .where(
                Opportunity.id == opp.id,
                Opportunity.visibility == "private",
                Opportunity.share_consent_at.is_not(None),
            )
            .values(
                visibility="public",
                made_public_at=now,
                made_public_by=admin.id,
                score_requested_at=now,
            )
            .execution_options(synchronize_session=False)
        ).rowcount
        if not done:
            db.rollback()
            raise HTTPException(409, NO_CONSENT)
        db.add(
            ChangeEvent(
                opportunity_id=opp.id,
                field="visibility",
                old={"visibility": "private"},
                new={"visibility": "public", "published_by": str(admin.id)},
                at=now,
            )
        )
        db.commit()
        db.refresh(opp)
    visible = bool(
        db.scalar(sa.select(member_visible_public()).where(Opportunity.id == opp.id))
    )
    return _items(db, [(opp, visible)])[0]
