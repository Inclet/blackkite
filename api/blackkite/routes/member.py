"""Member routes: feed, opportunity page, state and note, shortlist
(docs/api-contract.md section 2). Every route needs a session; every query is the
caller's own (member/view.py)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from blackkite.auth.deps import CurrentUser, DbDep, require_user
from blackkite.db.models import OPPORTUNITY_STATUSES, VERIFICATIONS
from blackkite.member import feed as F
from blackkite.member import schemas as S
from blackkite.member.view import opportunity_out

router = APIRouter(dependencies=[Depends(require_user)])

NOT_FOUND = "Opportunity not found"
Verification = Literal[VERIFICATIONS]  # type: ignore[valid-type]
Status = Literal[OPPORTUNITY_STATUSES]  # type: ignore[valid-type]
FitFilter = Literal["strong", "good", "possible"]


def now_utc() -> datetime:
    """Overridden in tests to freeze the clock."""
    return datetime.now(UTC)


Now = Annotated[datetime, Depends(now_utc)]


@router.get("/feed", response_model=S.FeedContent)
def get_feed(
    user: CurrentUser,
    db: DbDep,
    now: Now,
    stream: S.Stream | None = None,
    profile: uuid.UUID | None = None,
    window: Annotated[int | None, Query(ge=0, le=366)] = None,
    verification: Verification | None = None,
    source: uuid.UUID | None = None,
    state: S.State | None = None,
    status: Annotated[list[Status] | None, Query()] = None,
    fit: FitFilter | None = None,
) -> S.FeedContent:
    filters = F.FeedFilters(
        stream=stream,
        profile_id=profile,
        window=window,
        verification=verification,
        source_id=source,
        state=state,
        statuses=tuple(status) if status else None,
        fit=fit,
    )
    return F.feed_content(db, user, filters, now)


@router.get("/shortlist", response_model=list[S.FeedItem])
def get_shortlist(user: CurrentUser, db: DbDep, now: Now) -> list[S.FeedItem]:
    return F.shortlist(db, user, now)


@router.get("/opportunities/{opportunity_id}", response_model=S.OpportunityOut)
def get_opportunity(
    opportunity_id: uuid.UUID, user: CurrentUser, db: DbDep, now: Now
) -> S.OpportunityOut:
    row = F.one_row(db, user, opportunity_id)
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return opportunity_out(db, row, now)


@router.put("/opportunities/{opportunity_id}/state", response_model=S.UserStateOut)
def put_state(
    opportunity_id: uuid.UUID, body: S.StateIn, user: CurrentUser, db: DbDep
) -> S.UserStateOut:
    uo = F.set_state(db, user, opportunity_id, body)
    if uo is None:
        raise HTTPException(404, NOT_FOUND)
    db.commit()
    db.refresh(uo)
    return F.state_out(uo)


@router.put("/opportunities/{opportunity_id}/note", response_model=S.UserStateOut)
def put_note(
    opportunity_id: uuid.UUID, body: S.NoteIn, user: CurrentUser, db: DbDep
) -> S.UserStateOut:
    uo = F.set_note(db, user, opportunity_id, body)
    if uo is None:
        raise HTTPException(404, NOT_FOUND)
    db.commit()
    db.refresh(uo)
    return F.state_out(uo)
