"""Request/response models shared by routers."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from blackkite.member.schemas import CamelModel


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class VerifyOut(BaseModel):
    redirect: str


class Message(BaseModel):
    detail: str


class UserOut(BaseModel):
    """``GET /me`` (kept as it was: snake_case keys, read by the web app)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str | None
    role: str
    status: str
    created_at: datetime


class AdminUserOut(CamelModel):
    """A user as the admin users screen shows them (camelCase, like the rest of
    /api)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str | None
    role: str
    status: str
    created_at: datetime


class InviteOut(CamelModel):
    id: uuid.UUID
    email: str
    invited_by: uuid.UUID | None
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    status: str  # pending | expired | accepted
