"""Calendar routes (spec 8 "Calendar of deadlines and events";
docs/api-contract.md section 5)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from blackkite.auth.deps import CurrentUser, DbDep, require_user
from blackkite.member import calendar as C
from blackkite.member import schemas as S
from blackkite.routes.member import Now

router = APIRouter(dependencies=[Depends(require_user)])

TOO_LONG = f"The calendar shows at most {C.MAX_DAYS} days at a time."
BACKWARDS = "The end date must be on or after the start date."


@router.get("/calendar", response_model=S.CalendarOut)
def get_calendar(
    user: CurrentUser,
    db: DbDep,
    now: Now,
    first: Annotated[date, Query(alias="from")],
    last: Annotated[date, Query(alias="to")],
    kind: Literal["deadlines", "events", "all"] = "all",
    saved: bool = False,
) -> S.CalendarOut:
    if last < first:
        raise HTTPException(422, BACKWARDS)
    if (last - first).days + 1 > C.MAX_DAYS:
        raise HTTPException(422, TOO_LONG)
    return C.calendar(db, user, first, last, now, kind=kind, saved=saved)
