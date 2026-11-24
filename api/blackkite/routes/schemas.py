"""Request/response models shared by routers."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class VerifyOut(BaseModel):
    redirect: str


class Message(BaseModel):
    detail: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str | None
    role: str
    status: str
    created_at: datetime


class InviteOut(BaseModel):
    id: uuid.UUID
    email: str
    invited_by: uuid.UUID | None
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    status: str  # pending | expired | accepted
