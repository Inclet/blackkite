"""Database schema: CLAUDE.md section 6 (plus 4.1 for `source`, section 9 for sessions).

Per-user tables carry a non-null, indexed `user_id`; see PER_USER_TABLES.
"""

import secrets
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from blackkite.config import EMBEDDING_DIM
from blackkite.db.base import Base, created_at, enum, in_list_check, updated_at, uuid_pk

# --- Enumerations (values exactly as the spec names them) -------------------

STREAMS = ("tender", "investment", "funding", "event")
ROLES = ("member", "admin")
USER_STATUSES = ("active", "deactivated")
PROFILE_TYPES = ("business", "personal")
DIGEST_CHANNELS = ("email", "telegram")  # spec 8: email first, Telegram second
# Decision 18: weekly on Monday, or off. No other frequencies or weekdays in v1;
# adding one later is a CHECK swap (see enum() in db/base.py).
DIGEST_FREQUENCIES = ("weekly", "off")
DIGEST_DAYS = ("mon",)
# Urgent alerts by fit word (spec 8, spec 12: never the numeric score). NULL = off.
ALERT_MIN_FITS = ("strong", "good")
SOURCE_KINDS = ("original", "publisher", "aggregator", "news", "community")
SOURCE_STATUSES = ("suggested", "testing", "active", "paused", "retired")
COLLECTOR_TYPES = (
    "rss",
    "html_list",
    "browser_list",
    "json_api",
    "search_query",
    "email_ingest",
    "custom",
)
SOURCE_RUN_STATUSES = ("running", "succeeded", "failed")
SUGGESTION_STATUSES = ("suggested", "accepted", "rejected")
OPPORTUNITY_STATUSES = ("open", "closing_soon", "expired", "awarded", "cancelled")
VERIFICATIONS = ("verified_original", "aggregator_only", "unverified")
VISIBILITIES = ("public", "private")
USER_OPPORTUNITY_STATES = ("unseen", "saved", "dismissed", "acting", "done")

# Tables whose rows belong to one user. Every query on them filters by user_id.
PER_USER_TABLES = (
    "profile",
    "digest_setting",
    "source_suggestion",
    "user_source_mute",
    "user_opportunity",
    "user_opportunity_score",
    "digest_log",
    "alert_log",
    "session",
)


def _ts(nullable: bool = True) -> Mapped[Any]:
    return mapped_column(sa.DateTime(timezone=True), nullable=nullable)


def _user_fk(ondelete: str = "CASCADE") -> Mapped[uuid.UUID]:
    return mapped_column(
        sa.ForeignKey("user.id", ondelete=ondelete), nullable=False, index=True
    )


# --- Identity ----------------------------------------------------------------


# 16 random bytes as hex, in Python and (for rows inserted by SQL) in Postgres.
UNSUBSCRIBE_NONCE_SQL = "replace(gen_random_uuid()::text, '-', '')"


def new_unsubscribe_nonce() -> str:
    return secrets.token_hex(16)


class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        sa.Index("uq_user_email_lower", sa.text("lower(email)"), unique=True),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(sa.String(320), nullable=False)
    name: Mapped[str | None] = mapped_column(sa.String(200))
    role: Mapped[str] = mapped_column(
        enum(*ROLES, name="role"), nullable=False, server_default="member"
    )
    status: Mapped[str] = mapped_column(
        enum(*USER_STATUSES, name="status"), nullable=False, server_default="active"
    )
    # Per-user part of every unsubscribe link (decision 43, delivery/unsubscribe.py).
    # 32 hex characters; a new value revokes every link sent before.
    unsubscribe_nonce: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        default=new_unsubscribe_nonce,
        server_default=sa.text(UNSUBSCRIBE_NONCE_SQL),
    )
    # Per-user part of the signed calendar feed link (member/calendar_feed.py);
    # a new value revokes the old link. Separate from the unsubscribe nonce.
    calendar_nonce: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        default=new_unsubscribe_nonce,
        server_default=sa.text(UNSUBSCRIBE_NONCE_SQL),
    )
    # When the calendar link was last revoked; NULL = never.
    calendar_nonce_rotated_at: Mapped[datetime | None] = _ts()
    # When a session was last started (magic link spent). For the admin users
    # screen; NULL = never signed in.
    last_sign_in_at: Mapped[datetime | None] = _ts()
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class Invite(Base):
    __tablename__ = "invite"
    __table_args__ = (sa.Index("ix_invite_email_lower", sa.text("lower(email)")),)

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(sa.String(320), nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    # sha256 hex of the token sent in the invite email; the raw token is never stored.
    token_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = _ts(nullable=False)
    accepted_at: Mapped[datetime | None] = _ts()
    accepted_user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("user.id", ondelete="SET NULL"), index=True
    )


class LoginToken(Base):
    """A magic-link token. Single use, short-lived, stored hashed.

    Issued to an existing user (user_id) or to the holder of a pending invite (invite_id).
    """

    __tablename__ = "login_token"
    __table_args__ = (
        sa.CheckConstraint(
            "(user_id IS NOT NULL) <> (invite_id IS NOT NULL)", name="user_xor_invite"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    token_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    invite_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("invite.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = _ts(nullable=False)
    used_at: Mapped[datetime | None] = _ts()


class Session(Base):
    """Server-side session. The cookie carries a random id; only its sha256 is stored."""

    __tablename__ = "session"

    id: Mapped[uuid.UUID] = uuid_pk()
    token_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True)
    user_id: Mapped[uuid.UUID] = _user_fk()
    created_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = _ts(nullable=False)


class Profile(Base):
    __tablename__ = "profile"
    __table_args__ = (
        sa.UniqueConstraint("user_id", "name"),
        # Target for composite FKs that keep a profile reference inside one user's data.
        sa.UniqueConstraint("id", "user_id"),
        sa.Index(
            "ix_profile_backfill_requested_at",
            "backfill_requested_at",
            postgresql_where=sa.text("backfill_requested_at IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    type: Mapped[str] = mapped_column(enum(*PROFILE_TYPES, name="type"), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    # Pending backfill of match and score (spec 5), run by the worker off the
    # request path (scoring/backfill.py). NULL = nothing pending.
    backfill_requested_at: Mapped[datetime | None] = _ts()
    # Failed runs of the pending backfill; a new request resets it to 0.
    backfill_attempts: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )
    # The version whose scoring-relevant content was last fully scored. NULL =
    # never scored.
    scored_version: Mapped[int | None] = mapped_column(sa.Integer)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class DigestSetting(Base):
    __tablename__ = "digest_setting"
    __table_args__ = (
        sa.UniqueConstraint("user_id", "channel"),
        in_list_check("streams", STREAMS, "streams_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    channel: Mapped[str] = mapped_column(
        enum(*DIGEST_CHANNELS, name="channel"), nullable=False
    )
    address: Mapped[str] = mapped_column(sa.String(320), nullable=False)
    frequency: Mapped[str] = mapped_column(
        enum(*DIGEST_FREQUENCIES, name="frequency"),
        nullable=False,
        server_default="weekly",
    )
    day: Mapped[str] = mapped_column(
        enum(*DIGEST_DAYS, name="day"), nullable=False, server_default="mon"
    )
    # Lowest fit word that sends an urgent alert; NULL turns alerts off.
    alert_min_fit: Mapped[str | None] = mapped_column(
        enum(*ALERT_MIN_FITS, name="alert_min_fit")
    )
    # NULL means "the streams of the user's profiles".
    streams: Mapped[list[str] | None] = mapped_column(ARRAY(sa.String(32)))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


# --- Sources -------------------------------------------------------------------


class Source(Base):
    __tablename__ = "source"
    __table_args__ = (
        sa.UniqueConstraint("name"),
        in_list_check("streams", STREAMS, "streams_valid"),
        sa.CheckConstraint("cardinality(streams) >= 1", name="streams_not_empty"),
        sa.CheckConstraint(
            "rate_limit IS NULL OR rate_limit >= 1", name="rate_limit_min_1s"
        ),
        sa.Index("ix_source_status", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    home_url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    publisher: Mapped[str | None] = mapped_column(sa.String(200))
    streams: Mapped[list[str]] = mapped_column(ARRAY(sa.String(32)), nullable=False)
    kind: Mapped[str] = mapped_column(enum(*SOURCE_KINDS, name="kind"), nullable=False)
    collector_type: Mapped[str] = mapped_column(
        enum(*COLLECTOR_TYPES, name="collector_type"), nullable=False
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    # How often to run, as a cron expression (UTC). NULL = not scheduled yet.
    schedule: Mapped[str | None] = mapped_column(sa.String(100))
    # Minimum seconds between two requests to this source's host.
    rate_limit: Mapped[float | None] = mapped_column(sa.Float)
    access_note: Mapped[str | None] = mapped_column(sa.Text)
    status: Mapped[str] = mapped_column(
        enum(*SOURCE_STATUSES, name="status"), nullable=False, server_default="testing"
    )
    added_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    # When collector_type or config last changed. Promotion to active counts only
    # runs started after this (spec 4.3 step 4: two sane runs of the config being
    # promoted). NULL = unchanged since creation, every run counts.
    config_changed_at: Mapped[datetime | None] = _ts()
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class SourceRun(Base):
    __tablename__ = "source_run"
    __table_args__ = (
        sa.Index("ix_source_run_source_id_started_at", "source_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("source.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = created_at()
    finished_at: Mapped[datetime | None] = _ts()
    status: Mapped[str] = mapped_column(
        enum(*SOURCE_RUN_STATUSES, name="status"),
        nullable=False,
        server_default="running",
    )
    items_found: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )
    items_new: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )
    # Items rolled back by the pipeline (one bad item never sinks the run).
    items_failed: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )
    error: Mapped[str | None] = mapped_column(sa.Text)
    # Things a run skipped without failing, for the run's error log (decision
    # 49): a list of {kind, message, ...}; e.g. kind "email_no_link" with the
    # email's sender, subject and date (never its body).
    warnings: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )


class SourceStatusChange(Base):
    """A source's status history for the admin source screen (spec 4.4): one row
    per change, including creation (``old_status`` NULL) and the automatic move
    back to testing when an active source's config changes (decision 27).
    Admin audit data, shared, not per user; ``changed_by`` is NULL for system
    changes and after the admin's account is deleted."""

    __tablename__ = "source_status_change"
    __table_args__ = (
        sa.Index("ix_source_status_change_source_id_at", "source_id", "at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("source.id", ondelete="CASCADE"), nullable=False
    )
    old_status: Mapped[str | None] = mapped_column(
        enum(*SOURCE_STATUSES, name="old_status")
    )
    new_status: Mapped[str] = mapped_column(
        enum(*SOURCE_STATUSES, name="new_status"), nullable=False
    )
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    reason: Mapped[str | None] = mapped_column(sa.String(200))
    at: Mapped[datetime] = created_at()


class HttpCache(Base):
    """Last response per URL, for conditional GET (ETag / Last-Modified). Shared,
    not per user. Only responses that carry a validator are stored."""

    __tablename__ = "http_cache"

    url: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    etag: Mapped[str | None] = mapped_column(sa.Text)
    last_modified: Mapped[str | None] = mapped_column(sa.Text)
    content_type: Mapped[str | None] = mapped_column(sa.Text)
    content: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    fetched_at: Mapped[datetime] = created_at()


class SourceSuggestion(Base):
    __tablename__ = "source_suggestion"
    __table_args__ = (sa.Index("ix_source_suggestion_status", "status"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    note: Mapped[str | None] = mapped_column(sa.Text)
    status: Mapped[str] = mapped_column(
        enum(*SUGGESTION_STATUSES, name="status"),
        nullable=False,
        server_default="suggested",
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    reviewed_at: Mapped[datetime | None] = _ts()
    # The source created from this suggestion, if accepted.
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("source.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = created_at()


class UserSourceMute(Base):
    __tablename__ = "user_source_mute"

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("source.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = created_at()


# --- Catalogue (shared) -------------------------------------------------------------


class Opportunity(Base):
    __tablename__ = "opportunity"
    __table_args__ = (
        sa.CheckConstraint(
            "visibility <> 'private' OR owner_user_id IS NOT NULL",
            name="private_has_owner",
        ),
        sa.CheckConstraint(
            "made_public_at IS NULL OR visibility = 'public'",
            name="made_public_is_public",
        ),
        sa.CheckConstraint(
            "value_currency IS NULL OR value_currency ~ '^[A-Z]{3}$'",
            name="value_currency_iso",
        ),
        sa.Index("ix_opportunity_stream_status", "stream", "status"),
        sa.Index("ix_opportunity_deadline_at", "deadline_at"),
        sa.Index("ix_opportunity_event_start", "event_start"),
        sa.Index("ix_opportunity_tags", "tags", postgresql_using="gin"),
        sa.Index(
            "ix_opportunity_needs_review",
            "needs_review",
            postgresql_where=sa.text("needs_review"),
        ),
        sa.Index(
            "ix_opportunity_score_requested_at",
            "score_requested_at",
            postgresql_where=sa.text("score_requested_at IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    stream: Mapped[str] = mapped_column(enum(*STREAMS, name="stream"), nullable=False)
    subtype: Mapped[str | None] = mapped_column(sa.String(100))
    title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    organisation: Mapped[str | None] = mapped_column(sa.Text)
    # Short name for row subtitles (owner decision 5).
    organisation_short: Mapped[str | None] = mapped_column(sa.String(100))
    summary: Mapped[str | None] = mapped_column(sa.Text)
    published_at: Mapped[datetime | None] = _ts()
    deadline_at: Mapped[datetime | None] = _ts()
    event_start: Mapped[datetime | None] = _ts()
    event_end: Mapped[datetime | None] = _ts()
    value_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    value_currency: Mapped[str | None] = mapped_column(sa.String(3))
    value_note: Mapped[str | None] = mapped_column(sa.Text)
    location: Mapped[str | None] = mapped_column(sa.Text)
    eligibility: Mapped[str | None] = mapped_column(sa.Text)
    requirements: Mapped[list[Any] | None] = mapped_column(JSONB)
    submission_method: Mapped[str | None] = mapped_column(sa.Text)
    fees: Mapped[str | None] = mapped_column(sa.Text)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(sa.String(100)), nullable=False, server_default=sa.text("'{}'::varchar[]")
    )
    embedding: Mapped[Any | None] = mapped_column(Vector(EMBEDDING_DIM))
    # Supporting snippet per extracted field (spec 5 step 5, spec 10): {"deadline_at": "...", ...}
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        enum(*OPPORTUNITY_STATUSES, name="status"),
        nullable=False,
        server_default="open",
    )
    verification: Mapped[str] = mapped_column(
        enum(*VERIFICATIONS, name="verification"),
        nullable=False,
        server_default="unverified",
    )
    needs_review: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    visibility: Mapped[str] = mapped_column(
        enum(*VISIBILITIES, name="visibility"), nullable=False, server_default="public"
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    # Private manual items (spec 6): the link the owner gave, http(s) only. No
    # source row carries a manual item.
    manual_url: Mapped[str | None] = mapped_column(sa.Text)
    # Scoring queue run by the worker (worker/item_scores.py): set when a
    # private item is created or edited (scored for its owner only) or made
    # public (scored for everyone). NULL = nothing pending.
    score_requested_at: Mapped[datetime | None] = _ts()
    # Sharing a private manual item (spec 6): when the owner allowed an admin to
    # make it public (NULL = not allowed), and when and by whom it was made
    # public (NULL = never). Once public, owner_user_id is kept for attribution
    # only.
    share_consent_at: Mapped[datetime | None] = _ts()
    made_public_at: Mapped[datetime | None] = _ts()
    made_public_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class OpportunitySource(Base):
    __tablename__ = "opportunity_source"
    __table_args__ = (
        sa.UniqueConstraint("opportunity_id", "source_id", "url"),
        # At most one original per opportunity.
        sa.Index(
            "uq_opportunity_source_one_original",
            "opportunity_id",
            unique=True,
            postgresql_where=sa.text("is_original"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    is_original: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    first_seen: Mapped[datetime] = created_at()
    last_seen: Mapped[datetime] = created_at()


class Document(Base):
    __tablename__ = "document"

    id: Mapped[uuid.UUID] = uuid_pk()
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(sa.Text)
    extracted_text: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = created_at()


class ChangeEvent(Base):
    __tablename__ = "change_event"
    __table_args__ = (
        sa.Index("ix_change_event_opportunity_id_at", "opportunity_id", "at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False
    )
    field: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    old: Mapped[Any | None] = mapped_column(JSONB)
    new: Mapped[Any | None] = mapped_column(JSONB)
    at: Mapped[datetime] = created_at()


class Award(Base):
    """Awarded contract, from Umucyo awarded lists, for price benchmarking (spec 6).

    Shared, not per user. Collected by the ``umucyo_awards`` custom collector and
    written only by ``pipeline/awards.py`` (never into ``opportunity``). One row per
    (tender ref, procuring entity): ``ref_key`` is the normalised tender ref, or
    ``title:<normalised title>`` when the list gave no ref (a generic title also
    carries a digest of winner, amount and date); ``entity_key`` the
    normalised entity name ("" when unknown).
    """

    __tablename__ = "award"
    __table_args__ = (
        sa.UniqueConstraint("ref_key", "entity_key"),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="currency_iso"
        ),
        sa.CheckConstraint("amount IS NULL OR amount >= 0", name="amount_not_negative"),
        sa.Index("ix_award_tender_ref", "tender_ref"),
        sa.Index("ix_award_category_currency", "category", "currency"),
        sa.Index("ix_award_entity_key", "entity_key"),
        sa.Index("ix_award_awarded_on", "awarded_on"),
        sa.Index("ix_award_tags", "tags", postgresql_using="gin"),
        sa.Index("ix_award_source_ids", "source_ids", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tender_ref: Mapped[str | None] = mapped_column(sa.String(200))
    ref_key: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    title: Mapped[str | None] = mapped_column(sa.Text)
    entity: Mapped[str | None] = mapped_column(sa.Text)
    entity_key: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="")
    # [{"name": ...}, ...], as the source listed them
    bidders: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    # [{"bidder": ..., "amount": "123.00" | null, "currency": "RWF" | null}, ...]
    prices: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    winner: Mapped[str | None] = mapped_column(sa.Text)
    # The winning (contract) price and its currency; NULL when not stated.
    amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    currency: Mapped[str | None] = mapped_column(sa.String(3))
    # Contract period as listed (for example "12 months").
    period: Mapped[str | None] = mapped_column(sa.String(100))
    # Date the contract was awarded; only from a date with an explicit year.
    awarded_on: Mapped[date | None] = mapped_column(sa.Date)
    # Primary benchmark category (pipeline/categories.py) and every category tag
    # ("sector:<key>", the extraction tag vocabulary).
    category: Mapped[str] = mapped_column(
        sa.String(100), nullable=False, server_default="other"
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(sa.String(100)), nullable=False, server_default=sa.text("'{}'::varchar[]")
    )
    url: Mapped[str | None] = mapped_column(sa.Text)
    # The tender in the catalogue, when it is there (by tender ref or close
    # title and entity).
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("opportunity.id", ondelete="SET NULL"), index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("source.id", ondelete="SET NULL"), index=True
    )
    # Every source that has listed the record (source_id is the first); its
    # visibility follows any of them (records.record_visible).
    source_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(sa.Uuid()), nullable=False, server_default=sa.text("'{}'::uuid[]")
    )
    # The values as listed ({field: text}), and what normalising left out
    # ("problems": [...]). Supporting text for every stored amount and date.
    raw: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    first_seen: Mapped[datetime] = created_at()
    last_seen: Mapped[datetime] = created_at()
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class ProcurementPlanItem(Base):
    """A planned tender from a procurement plan (spec 2.6: tenders before they are
    advertised). Shared, not per user; written only by ``pipeline/plans.py``.

    One row per (entity, description, fiscal year), on their normalised keys.
    ``planned_start``/``planned_end`` are the planned period as dates: from a
    stated date, or from a quarter with an explicit fiscal or calendar year;
    NULL when the plan does not say (never guessed). ``opportunity_id`` is set
    once the actual tender appears in the catalogue.
    """

    __tablename__ = "procurement_plan_item"
    __table_args__ = (
        sa.UniqueConstraint(
            "entity_key",
            "description_key",
            "fiscal_year",
            postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="currency_iso"
        ),
        sa.CheckConstraint(
            "estimated_amount IS NULL OR estimated_amount >= 0",
            name="estimated_amount_not_negative",
        ),
        sa.CheckConstraint(
            "planned_quarter IS NULL OR planned_quarter IN ('Q1', 'Q2', 'Q3', 'Q4')",
            name="planned_quarter_valid",
        ),
        sa.CheckConstraint(
            "(planned_start IS NULL) = (planned_end IS NULL) "
            "AND (planned_start IS NULL OR planned_start <= planned_end)",
            name="planned_period_valid",
        ),
        sa.Index("ix_procurement_plan_item_category", "category"),
        sa.Index("ix_procurement_plan_item_entity_key", "entity_key"),
        sa.Index(
            "ix_procurement_plan_item_planned_start_planned_end",
            "planned_start",
            "planned_end",
        ),
        sa.Index("ix_procurement_plan_item_tags", "tags", postgresql_using="gin"),
        sa.Index(
            "ix_procurement_plan_item_source_ids",
            "source_ids",
            postgresql_using="gin",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    entity: Mapped[str] = mapped_column(sa.Text, nullable=False)
    entity_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    description_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    category: Mapped[str] = mapped_column(
        sa.String(100), nullable=False, server_default="other"
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(sa.String(100)), nullable=False, server_default=sa.text("'{}'::varchar[]")
    )
    # Procurement method as listed (for example "Open competitive bidding").
    method: Mapped[str | None] = mapped_column(sa.Text)
    estimated_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    currency: Mapped[str | None] = mapped_column(sa.String(3))
    # "2026/27" (Rwanda's fiscal year runs July to June); NULL when not stated.
    fiscal_year: Mapped[str | None] = mapped_column(sa.String(7))
    planned_quarter: Mapped[str | None] = mapped_column(sa.String(2))
    planned_date: Mapped[date | None] = mapped_column(sa.Date)
    planned_start: Mapped[date | None] = mapped_column(sa.Date)
    planned_end: Mapped[date | None] = mapped_column(sa.Date)
    tender_ref: Mapped[str | None] = mapped_column(sa.String(200))
    url: Mapped[str | None] = mapped_column(sa.Text)
    embedding: Mapped[Any | None] = mapped_column(Vector(EMBEDDING_DIM))
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("opportunity.id", ondelete="SET NULL"), index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("source.id", ondelete="SET NULL"), index=True
    )
    # Every source that has listed the record (source_id is the first); its
    # visibility follows any of them (records.record_visible).
    source_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(sa.Uuid()), nullable=False, server_default=sa.text("'{}'::uuid[]")
    )
    raw: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    first_seen: Mapped[datetime] = created_at()
    last_seen: Mapped[datetime] = created_at()
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


# --- Per user ------------------------------------------------------------------------


class UserOpportunity(Base):
    """A user's state for one opportunity, across all their profiles (decision 19).

    Saving, dismissing, acting, done and the note apply to the opportunity for this
    user, whichever profile surfaced it. Per-profile scores live in
    UserOpportunityScore. No row means `unseen`.
    """

    __tablename__ = "user_opportunity"
    __table_args__ = (
        sa.UniqueConstraint("user_id", "opportunity_id"),
        sa.Index("ix_user_opportunity_user_id_state", "user_id", "state"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(
        enum(*USER_OPPORTUNITY_STATES, name="state"),
        nullable=False,
        server_default="unseen",
    )
    dismiss_reason: Mapped[str | None] = mapped_column(sa.Text)
    note: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class UserOpportunityScore(Base):
    """Score of one opportunity against one of the user's profiles (spec 7)."""

    __tablename__ = "user_opportunity_score"
    __table_args__ = (
        sa.UniqueConstraint("user_id", "opportunity_id", "profile_id"),
        # The profile must belong to the same user.
        sa.ForeignKeyConstraint(
            ["profile_id", "user_id"],
            ["profile.id", "profile.user_id"],
            name="fk_user_opportunity_score_profile_owner",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "score IS NULL OR score BETWEEN 0 AND 100", name="score_range"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False, index=True)
    score: Mapped[int | None] = mapped_column(sa.SmallInteger)
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    score_reason: Mapped[str | None] = mapped_column(sa.Text)
    # scoring.service.profile_hash of the profile when this row was written: the
    # key for reusing its model judgement (a rename does not change it). NULL for
    # rows written before it existed.
    profile_hash: Mapped[str | None] = mapped_column(sa.String(64))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class DigestLog(Base):
    """One weekly digest per user per Kigali day (``digest_date``; the unique key
    makes the job idempotent). ``details`` keeps what each item looked like when it
    went out, so the next digest can skip items that have not changed:
    ``{"items": [{"id", "profile_id", "deadline_at", "value_amount",
    "value_currency"}], "closing": [ids], "more_count": n}``."""

    __tablename__ = "digest_log"
    __table_args__ = (
        sa.Index("ix_digest_log_user_id_sent_at", "user_id", "sent_at"),
        sa.UniqueConstraint("user_id", "digest_date"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    sent_at: Mapped[datetime] = created_at()
    digest_date: Mapped[date] = mapped_column(
        sa.Date,
        nullable=False,
        server_default=sa.text("((now() AT TIME ZONE 'Africa/Kigali')::date)"),
    )
    opportunity_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(sa.Uuid), nullable=False, server_default=sa.text("'{}'::uuid[]")
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )


class AlertLog(Base):
    """Urgent alerts sent (spec 8): at most one per (user, opportunity), ever."""

    __tablename__ = "alert_log"
    __table_args__ = (sa.UniqueConstraint("user_id", "opportunity_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The profile it matched; kept as a plain id (the profile may be deleted later).
    profile_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)
    sent_at: Mapped[datetime] = created_at()
