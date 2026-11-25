"""The caller's own account: digest settings (decision 18: weekly on Monday, or
off), display name (the digest and feed greet people by first name), and export
and deletion (spec 10)."""

from __future__ import annotations

from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field, field_validator

from blackkite.auth.deps import CurrentUser, DbDep, SettingsDep, require_user
from blackkite.db.models import DigestSetting, User
from blackkite.member import privacy
from blackkite.member.schemas import CamelIn, CamelModel
from blackkite.routes.schemas import UserOut

router = APIRouter(dependencies=[Depends(require_user)])

Stream = Literal["tender", "investment", "funding", "event"]
AlertMinFit = Literal["strong", "good"]


class DigestSettingsIn(CamelIn):
    channel: Literal["email"] = "email"
    frequency: Literal["weekly", "off"]
    day: Literal["mon"] = "mon"
    # Urgent alerts for items whose best active profile's fit word is at least
    # this ("strong" > "good"); null turns alerts off. Never the numeric score.
    alert_min_fit: AlertMinFit | None = None
    # null: the streams of the user's profiles.
    streams: Annotated[list[Stream], Field(min_length=1)] | None = None

    @field_validator("streams")
    @classmethod
    def _unique(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(set(v)) != len(v):
            raise ValueError("streams must not repeat")
        return v


class DigestSettingsOut(CamelModel):
    channel: str
    frequency: str
    day: str
    alert_min_fit: AlertMinFit | None
    streams: list[str] | None


class NameIn(CamelIn):
    name: Annotated[str, Field(min_length=1, max_length=200)] | None


def email_setting(db: DbDep, user: User) -> DigestSetting | None:
    return db.scalar(
        sa.select(DigestSetting).where(
            DigestSetting.user_id == user.id, DigestSetting.channel == "email"
        )
    )


def _out(s: DigestSetting | None) -> DigestSettingsOut:
    if s is None:
        return DigestSettingsOut(
            channel="email",
            frequency="weekly",
            day="mon",
            alert_min_fit=None,
            streams=None,
        )
    return DigestSettingsOut(
        channel=s.channel,
        frequency=s.frequency,
        day=s.day,
        alert_min_fit=s.alert_min_fit,  # type: ignore[arg-type]
        streams=s.streams,
    )


@router.get("/digest-settings", response_model=DigestSettingsOut)
def get_digest_settings(user: CurrentUser, db: DbDep) -> DigestSettingsOut:
    return _out(email_setting(db, user))


@router.put("/digest-settings", response_model=DigestSettingsOut)
def put_digest_settings(
    body: DigestSettingsIn, user: CurrentUser, db: DbDep
) -> DigestSettingsOut:
    s = email_setting(db, user)
    if s is None:
        # The address is the account's own; it is not editable here.
        s = DigestSetting(user_id=user.id, channel="email", address=user.email)
        db.add(s)
    s.frequency = body.frequency
    s.day = body.day
    s.alert_min_fit = body.alert_min_fit
    s.streams = body.streams
    db.commit()
    return _out(s)


@router.patch("/me", response_model=UserOut)
def set_name(body: NameIn, user: CurrentUser, db: DbDep) -> UserOut:
    user.name = body.name.strip() if body.name else None
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/me/export")
def export_me(user: CurrentUser, db: DbDep) -> dict:
    return privacy.export(db, user)


@router.delete("/me", status_code=204)
def delete_me(user: CurrentUser, db: DbDep, settings: SettingsDep) -> Response:
    try:
        privacy.delete_account(db, user)
    except privacy.LastAdmin:
        raise HTTPException(
            409, "You are the only admin. Make someone else an admin first."
        ) from None
    resp = Response(status_code=204)
    resp.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return resp
