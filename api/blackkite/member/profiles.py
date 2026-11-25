"""Profile data shapes (spec 7) and the profile service.

``profile.data`` is stored with snake_case keys (the seed in spec 7.1 and the
scoring track read it that way); the API speaks camelCase. Unknown keys are
refused so a typo never silently drops a requirement. ``null`` means "not yet
provided" and is kept as given (spec 7: missing data never hard-filters).

Every edit bumps ``version``. Match and score (spec 5) are not run here: a
backfill is requested and the worker runs it off the request path
(scoring/backfill.py). Only scoring-relevant changes ask for one: creating an
active profile, changing its type or data while active, or activating a profile
not yet scored at its version. A rename or deactivation asks for nothing; when
the profile was up to date, it stays up to date (``scored_version`` follows).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

import sqlalchemy as sa
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from blackkite.db.models import Profile, User
from blackkite.member.schemas import CamelIn, CamelModel
from blackkite.scoring.backfill import request_backfill

Stream = Literal["tender", "investment", "funding", "event"]
Text = Annotated[str, Field(min_length=1, max_length=200)]
TextList = Annotated[list[Text], Field(max_length=50)]
Amount = Annotated[int, Field(ge=0, le=10**15)]


class _Data(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class Range(_Data):
    min: Amount | None = None
    max: Amount | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Range:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min is above max")
        return self


class Capacity(_Data):
    model: Text | None = None  # e.g. "partner network"
    trucks_in_network: Amount | None = None
    refrigerated_in_network: Amount | None = None
    owned_trucks: Amount | None = None
    # A figure or a range, in tonnes (still open for Ironji, spec 13.2).
    tonnage: Annotated[float, Field(ge=0)] | Range | None = None


class Exclusions(_Data):
    organisations: TextList | None = None
    sectors: TextList | None = None
    keywords: TextList | None = None


class _Common(_Data):
    streams: Annotated[list[Stream], Field(min_length=1)]
    location: Text | None = None
    locations: TextList | None = None
    exclusions: Exclusions | None = None
    # The profile is a placeholder set the owner has yet to confirm (spec 7.1).
    provisional: bool | None = None

    @field_validator("streams")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("streams must not repeat")
        return v


class BusinessData(_Common):
    services: TextList | None = None
    sectors: TextList | None = None
    capacity: Capacity | None = None
    registrations_held: TextList | None = None
    registrations_not_held: TextList | None = None
    min_contract_rwf: Amount | None = None


class PersonalData(_Common):
    instruments: TextList | None = None
    ticket_range_rwf: Range | None = None
    horizon: Text | None = None
    event_topics: TextList | None = None
    availability: Text | None = None
    budget_rwf: Amount | None = None


DATA_MODELS: dict[str, type[_Common]] = {
    "business": BusinessData,
    "personal": PersonalData,
}


def validate_data(type_: str, data: dict[str, Any]) -> dict[str, Any]:
    """Validated data in storage form (snake_case, only the keys given)."""
    model = DATA_MODELS[type_].model_validate(data)
    return model.model_dump(mode="json", by_alias=False, exclude_unset=True)


def data_out(type_: str, data: dict[str, Any]) -> dict[str, Any]:
    """Stored data in API form (camelCase)."""
    try:
        model = DATA_MODELS[type_].model_validate(data)
    except (ValidationError, KeyError):
        return {to_camel(k): v for k, v in data.items()}
    return model.model_dump(mode="json", by_alias=True, exclude_unset=True)


# --- API models ------------------------------------------------------------------------

ProfileType = Literal["business", "personal"]
Name = Annotated[str, Field(min_length=1, max_length=200)]


class ProfileIn(CamelIn):
    name: Name
    type: ProfileType
    data: dict[str, Any]
    active: bool = True


class ProfilePatch(CamelIn):
    name: Name | None = None
    type: ProfileType | None = None
    data: dict[str, Any] | None = None
    active: bool | None = None


class ProfileOut(CamelModel):
    id: uuid.UUID
    name: str
    type: str
    data: dict[str, Any]
    version: int
    active: bool
    created_at: Any
    updated_at: Any


def profile_out(p: Profile) -> ProfileOut:
    return ProfileOut(
        id=p.id,
        name=p.name,
        type=p.type,
        data=data_out(p.type, p.data or {}),
        version=p.version,
        active=p.active,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


# --- service --------------------------------------------------------------------------


class NameTaken(Exception):
    pass


def list_profiles(db: Session, user: User) -> list[Profile]:
    return list(
        db.scalars(
            sa.select(Profile)
            .where(Profile.user_id == user.id)
            .order_by(Profile.created_at, Profile.name)
        )
    )


def get_profile(db: Session, user: User, profile_id: uuid.UUID) -> Profile | None:
    return db.scalar(
        sa.select(Profile).where(Profile.id == profile_id, Profile.user_id == user.id)
    )


def _name_taken(
    db: Session, user: User, name: str, except_id: uuid.UUID | None = None
) -> bool:
    q = sa.select(Profile.id).where(Profile.user_id == user.id, Profile.name == name)
    if except_id is not None:
        q = q.where(Profile.id != except_id)
    return db.scalar(q) is not None


def _now() -> datetime:
    return datetime.now(UTC)


def create_profile(
    db: Session, user: User, body: ProfileIn, now: datetime | None = None
) -> Profile:
    name = body.name.strip()
    if _name_taken(db, user, name):
        raise NameTaken(name)
    p = Profile(
        user_id=user.id,
        name=name,
        type=body.type,
        data=validate_data(body.type, body.data),
        active=body.active,
    )
    if p.active:
        request_backfill(p, now or _now())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def update_profile(
    db: Session,
    user: User,
    p: Profile,
    body: ProfilePatch,
    now: datetime | None = None,
) -> Profile:
    new_type = body.type or p.type
    if body.type is not None and body.type != p.type and body.data is None:
        raise ValueError("changing the type needs new data for that type")
    renamed = content_changed = activated = deactivated = False
    if body.name is not None and body.name.strip() != p.name:
        name = body.name.strip()
        if _name_taken(db, user, name, except_id=p.id):
            raise NameTaken(name)
        p.name = name
        renamed = True
    if body.data is not None:
        data = validate_data(new_type, body.data)
        if data != p.data or new_type != p.type:
            p.type = new_type
            p.data = data
            content_changed = True
    if body.active is not None and body.active != p.active:
        p.active = body.active
        activated, deactivated = body.active, not body.active
    if not (renamed or content_changed or activated or deactivated):
        return p
    up_to_date = p.scored_version is not None and p.scored_version == p.version
    p.version = p.version + 1
    if content_changed:
        if p.active:
            request_backfill(p, now or _now())
    elif up_to_date:
        # Name and active do not change scores: still scored at this version.
        p.scored_version = p.version
    elif activated:
        request_backfill(p, now or _now())
    db.commit()
    db.refresh(p)
    return p


def delete_profile(db: Session, p: Profile) -> None:
    """Its score rows go with it (FK cascade); states are per user and stay."""
    db.delete(p)
    db.commit()
