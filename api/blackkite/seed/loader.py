"""Idempotent loaders behind `bk bootstrap` and `bk seed-sources`. Callers commit."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.resources import files
from typing import Any

import sqlalchemy as sa
import yaml
from sqlalchemy.orm import Session as DB

from blackkite.auth.service import check_email, find_user_by_email
from blackkite.db.models import DigestSetting, Profile, Source, User
from blackkite.seed.sources import SEED_SOURCES

# Profile columns; every other YAML field goes into profile.data unchanged.
PROFILE_COLUMNS = ("name", "type")


def load_seed_profiles() -> dict[str, Any]:
    return yaml.safe_load(
        files("blackkite.seed").joinpath("profiles.yaml").read_text("utf-8")
    )


@dataclass
class BootstrapResult:
    user: User
    created_user: bool = False
    created_profiles: list[str] = field(default_factory=list)
    created_digest: bool = False


def bootstrap(db: DB, email: str | None) -> BootstrapResult:
    if not email or not email.strip():
        raise ValueError("BK_FIRST_ADMIN_EMAIL is not set")
    email = check_email(email, setting="BK_FIRST_ADMIN_EMAIL")
    user = find_user_by_email(db, email)
    created = user is None
    if user is None:
        user = User(email=email, role="admin", status="active")
        db.add(user)
        db.flush()
    elif user.role != "admin":
        user.role = "admin"
    result = BootstrapResult(user=user, created_user=created)

    seed = load_seed_profiles()
    existing = set(
        db.scalars(sa.select(Profile.name).where(Profile.user_id == user.id))
    )
    for entry in seed["profiles"]:
        if entry["name"] in existing:
            continue
        data = {k: v for k, v in entry.items() if k not in PROFILE_COLUMNS}
        # Spec 5: a new user's profiles are backfilled, by the worker.
        db.add(
            Profile(
                user_id=user.id,
                name=entry["name"],
                type=entry["type"],
                data=data,
                backfill_requested_at=datetime.now(UTC),
            )
        )
        result.created_profiles.append(entry["name"])

    digest = seed["digest"]
    has_digest = db.scalar(
        sa.select(DigestSetting.id).where(
            DigestSetting.user_id == user.id, DigestSetting.channel == digest["channel"]
        )
    )
    if has_digest is None:
        db.add(
            DigestSetting(
                user_id=user.id,
                channel=digest["channel"],
                address=email,
                frequency=digest["frequency"],
                day="mon",  # decision 18: weekly on Monday by default
            )
        )
        result.created_digest = True
    db.flush()
    return result


def seed_sources(db: DB) -> list[str]:
    """Insert missing seed sources as `testing`. Existing rows (by name) are left as they are."""
    admin_id = db.scalar(
        sa.select(User.id)
        .where(User.role == "admin")
        .order_by(User.created_at)
        .limit(1)
    )
    existing = set(db.scalars(sa.select(Source.name)))
    created = []
    for spec in SEED_SOURCES:
        if spec["name"] in existing:
            continue
        db.add(Source(**spec, status="testing", added_by=admin_id))
        created.append(spec["name"])
    db.flush()
    return created
