"""Private manual items: POST/PATCH/DELETE /api/items (spec 6;
docs/api-contract.md section 5). Owner only: any other caller, admins included,
gets 404. Refusals (422) answer ``{detail, errors}`` in plain words
(routes/refusals.py)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response

from blackkite.auth.deps import CurrentUser, DbDep, require_user
from blackkite.member import feed as F
from blackkite.member import items as I
from blackkite.member import schemas as S
from blackkite.member.view import opportunity_out
from blackkite.routes.member import Now
from blackkite.routes.refusals import Refusal, RefusalRoute

router = APIRouter(
    prefix="/items", dependencies=[Depends(require_user)], route_class=RefusalRoute
)

NOT_FOUND = "Item not found"


def _out(db, user, item_id: uuid.UUID, now) -> S.OpportunityOut:
    row = F.one_row(db, user, item_id)
    if row is None:  # pragma: no cover - the caller's own item is always visible
        raise HTTPException(404, NOT_FOUND)
    return opportunity_out(db, row, now)


@router.post("", status_code=201, response_model=S.OpportunityOut)
def create_item(
    body: I.ItemIn, user: CurrentUser, db: DbDep, now: Now
) -> S.OpportunityOut:
    try:
        opp = I.create_item(db, user, body, now)
    except I.ItemInvalid as e:
        raise Refusal(422, e.problems) from None
    db.commit()
    return _out(db, user, opp.id, now)


@router.patch("/{item_id}", response_model=S.OpportunityOut)
def update_item(
    item_id: uuid.UUID, body: I.ItemPatch, user: CurrentUser, db: DbDep, now: Now
) -> S.OpportunityOut:
    opp = I.own_item(db, user, item_id)
    if opp is None:
        raise HTTPException(404, NOT_FOUND)
    try:
        I.update_item(db, user, opp, body, now)
    except I.ItemInvalid as e:
        db.rollback()
        raise Refusal(422, e.problems) from None
    db.commit()
    return _out(db, user, opp.id, now)


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: uuid.UUID, user: CurrentUser, db: DbDep) -> Response:
    opp = I.own_item(db, user, item_id)
    if opp is None:
        raise HTTPException(404, NOT_FOUND)
    I.delete_item(db, user, opp)
    db.commit()
    return Response(status_code=204)
