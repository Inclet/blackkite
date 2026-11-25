"""Declarative base, naming convention and column helpers."""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


def enum(*values: str, name: str) -> sa.Enum:
    """A string column limited to `values` by a CHECK constraint.

    Non-native (VARCHAR + CHECK) rather than a Postgres ENUM type: adding a value
    later is a plain constraint swap, and downgrades leave no stray types behind.
    """
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        validate_strings=True,
    )


def in_list_check(
    column: str, values: tuple[str, ...], name: str
) -> sa.CheckConstraint:
    """CHECK that every element of a varchar[] column is one of `values`."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return sa.CheckConstraint(f"{column} <@ ARRAY[{quoted}]::varchar[]", name=name)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )


def created_at() -> Mapped[datetime]:
    return mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def updated_at() -> Mapped[datetime]:
    return mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
