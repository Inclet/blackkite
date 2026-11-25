"""Digest settings (decision 18: weekly on Monday, or off) and the caller's
display name (the digest and feed greet people by first name)."""

from __future__ import annotations

from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import Field, field_validator

from blackkite.auth.deps import CurrentUser, DbDep, require_user
from blackkite.db.models import DigestSetting, User
from blackkite.member.schemas import CamelIn, CamelModel
from blackkite.routes.schemas import UserOut

router = APIRouter(dependencies=[Depends(require_user)])

Stream = Literal["tender", "investment", "funding", "event"]


class DigestSettingsIn(CamelIn):
    channel: Literal["email"] = "email"
    frequency: Literal["weekly", "off"]
    day: Literal["mon"] = "mon"
    # Urgent alerts for items scoring above this (0-100); null turns alerts off.
    alert_threshold: Annotated[int, Field(ge=0, le=100)] | None = None
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
    alert_threshold: int | None
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
            alert_threshold=None,
            streams=None,
        )
    return DigestSettingsOut(
        channel=s.channel,
        frequency=s.frequency,
        day=s.day,
        alert_threshold=s.alert_threshold,
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
    s.alert_threshold = body.alert_threshold
    s.streams = body.streams
    db.commit()
    return _out(s)


@router.patch("/me", response_model=UserOut)
def set_name(body: NameIn, user: CurrentUser, db: DbDep) -> UserOut:
    user.name = body.name.strip() if body.name else None
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)
