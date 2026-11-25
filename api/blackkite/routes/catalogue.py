"""Admin bare catalogue (spec 11 M1) and the needs_review queue (spec 3).

Lists every public item, including those carried only by testing sources (which
members do not see; ``memberVisible`` says which). Private items are never listed
here (spec 10: admins manage sources and users, not other users' items).
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
from blackkite.pipeline.visibility import carried_by_visible_source

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
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CataloguePage:
    where = [Opportunity.visibility == "public"]
    if needs_review is not None:
        where.append(Opportunity.needs_review.is_(needs_review))
    if stream:
        where.append(Opportunity.stream == stream)
    total = db.scalar(sa.select(sa.func.count()).select_from(Opportunity).where(*where))
    rows = db.execute(
        sa.select(Opportunity, carried_by_visible_source())
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
        db.scalar(
            sa.select(carried_by_visible_source()).where(Opportunity.id == opp.id)
        )
    )
    return _items(db, [(opp, visible)])[0]
