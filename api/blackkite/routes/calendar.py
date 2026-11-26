"""Calendar routes (spec 8 "Calendar of deadlines and events";
docs/api-contract.md section 5)."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from blackkite.auth.deps import CurrentUser, DbDep, SettingsDep, require_user
from blackkite.auth.ratelimit import SlidingWindowLimiter
from blackkite.config import Settings
from blackkite.member import calendar as C
from blackkite.member import calendar_feed as CF
from blackkite.member import ics
from blackkite.member import schemas as S
from blackkite.routes.member import Now

# Session routes. The .ics feed itself is on ``feed_router`` (no session).
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


# --- personal calendar feed ------------------------------------------------------------

NOT_SET_UP = "Calendar feeds are not set up on this server yet."
FEED_NOT_FOUND = "This calendar link is not valid any more."
TOO_MANY = "Too many requests for this calendar link. Try again later."
ICS_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Disposition": 'inline; filename="blackkite.ics"',
    "X-Robots-Tag": "noindex",
}


class FeedLinkOut(S.CamelModel):
    """The caller's personal calendar link (https and webcal forms)."""

    url: str
    webcal_url: str
    # When the link was last revoked; null = never.
    rotated_at: datetime | None


def _link_out(settings: Settings, user) -> FeedLinkOut:
    try:
        url = CF.feed_url(settings, user)
    except CF.CalendarNotConfigured:
        raise HTTPException(503, NOT_SET_UP) from None
    return FeedLinkOut(
        url=url,
        webcal_url=CF.webcal_url(url),
        rotated_at=user.calendar_nonce_rotated_at,
    )


@router.get("/calendar/feed-link", response_model=FeedLinkOut)
def get_feed_link(user: CurrentUser, settings: SettingsDep) -> FeedLinkOut:
    return _link_out(settings, user)


@router.post("/calendar/feed-link/rotate", response_model=FeedLinkOut)
def rotate_feed_link(
    user: CurrentUser, db: DbDep, settings: SettingsDep, now: Now
) -> FeedLinkOut:
    if not CF.configured(settings):
        raise HTTPException(503, NOT_SET_UP)
    CF.rotate(user, now)
    db.commit()
    db.refresh(user)
    return _link_out(settings, user)


# No session: calendar apps fetch the link on their own; the token is the
# authority (member/calendar_feed.py).
feed_router = APIRouter()


def get_calendar_limiter(request: Request) -> SlidingWindowLimiter:
    return request.app.state.calendar_limiter


@feed_router.get("/calendar.ics", include_in_schema=False)
def get_ics(
    db: DbDep,
    settings: SettingsDep,
    limiter: Annotated[SlidingWindowLimiter, Depends(get_calendar_limiter)],
    token: Annotated[str, Query(max_length=200)] = "",
) -> Response:
    key = hashlib.sha256(token.encode("utf-8", "replace")).hexdigest()
    if not limiter.would_allow(key):
        raise HTTPException(429, TOO_MANY)
    limiter.hit(key)
    if not CF.configured(settings):
        raise HTTPException(404, FEED_NOT_FOUND)
    user = CF.user_for_token(db, settings, token)
    if user is None:
        raise HTTPException(404, FEED_NOT_FOUND)
    body = ics.render(db, user, settings.web_base_url)
    return Response(
        body, media_type="text/calendar; charset=utf-8", headers=ICS_HEADERS
    )
