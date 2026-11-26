"""Request/response models for source routes (spec 4).

JSON is camelCase like the rest of the API (docs/api-contract.md section 2);
request bodies also accept snake_case keys. A source's ``config`` object is data
for its collector and keeps the collector's own keys (``list_url``, ...).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from blackkite.collectors.problems import FieldValueError
from blackkite.collectors.registry import validate_config
from blackkite.member.schemas import CamelIn, CamelModel
from blackkite.sources.service import parse_schedule
from blackkite.sources.urlsafety import UnsafeURL, check_url

Stream = Literal["tender", "investment", "funding", "event"]
Kind = Literal["original", "publisher", "aggregator", "news", "community"]
CollectorType = Literal[
    "rss",
    "html_list",
    "browser_list",
    "json_api",
    "search_query",
    "email_ingest",
    "custom",
]
SourceStatus = Literal["suggested", "testing", "active", "paused", "retired"]
Health = Literal["ok", "degraded", "failing", "unknown"]

Name = Annotated[str, Field(min_length=1, max_length=200)]
Publisher = Annotated[str, Field(max_length=200)]
Note = Annotated[str, Field(max_length=5000)]
# Seconds between two requests to one host; at least 1 s (spec 10, politeness).
RateLimit = Annotated[float, Field(ge=1.0, le=3600)]
Streams = Annotated[list[Stream], Field(min_length=1, max_length=4)]
ORIGINAL_SEARCH_QUERY = (
    "a search_query source cannot be kind 'original': search results are never "
    "the issuer itself"
)


def _url(v: str | None) -> str | None:
    if v is None:
        return v
    try:
        check_url(v)
    except UnsafeURL as e:
        raise ValueError(str(e)) from None
    return v


def _schedule(v: str | None) -> str | None:
    if v is None:
        return v
    parse_schedule(v)
    return v.strip()


def _config(ctype: str, config: dict[str, Any]) -> dict[str, Any]:
    try:
        return validate_config(ctype, config)
    except TypeError as e:
        raise FieldValueError.at(("config",), str(e)) from None


class _SourceFields(CamelIn):
    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("home_url", check_fields=False)
    @classmethod
    def _home_url(cls, v):
        return _url(v)

    @field_validator("schedule", check_fields=False)
    @classmethod
    def _sched(cls, v):
        return _schedule(v)

    @field_validator("streams", check_fields=False)
    @classmethod
    def _streams(cls, v):
        if v is not None and len(set(v)) != len(v):
            raise ValueError("streams must not repeat")
        return v


class SourceIn(_SourceFields):
    name: Name
    home_url: str
    publisher: Publisher | None = None
    streams: Streams
    kind: Kind
    collector_type: CollectorType
    config: dict[str, Any] = Field(default_factory=dict)
    schedule: str | None = None
    rate_limit: RateLimit | None = None
    access_note: Note | None = None
    # Accepted suggestion this source was created from (links the two).
    suggestion_id: uuid.UUID | None = None

    # A field validator (not an after-model one), so config problems are
    # reported alongside problems in the other fields.
    @field_validator("config")
    @classmethod
    def _check_config(cls, v, info: ValidationInfo):
        ctype = info.data.get("collector_type")
        return v if ctype is None else _config(ctype, v)

    @model_validator(mode="after")
    def _check_kind(self):
        if self.kind == "original" and self.collector_type == "search_query":
            raise FieldValueError.at(("kind",), ORIGINAL_SEARCH_QUERY)
        return self


class SourcePatch(_SourceFields):
    """Edit. Status changes go through POST /api/admin/sources/{id}/status."""

    name: Name | None = None
    home_url: str | None = None
    publisher: Publisher | None = None
    streams: Streams | None = None
    kind: Kind | None = None
    collector_type: CollectorType | None = None
    config: dict[str, Any] | None = None
    schedule: str | None = None
    rate_limit: RateLimit | None = None
    access_note: Note | None = None


class PreviewIn(CamelIn):
    """Unsaved config for a test run."""

    collector_type: CollectorType
    config: dict[str, Any]
    home_url: str | None = None
    streams: Streams = Field(default_factory=lambda: ["tender"])
    rate_limit: RateLimit | None = None

    @field_validator("home_url")
    @classmethod
    def _home_url(cls, v):
        return _url(v)

    @field_validator("config")
    @classmethod
    def _check_config(cls, v, info: ValidationInfo):
        ctype = info.data.get("collector_type")
        return v if ctype is None else _config(ctype, v)


class StatusIn(CamelIn):
    status: SourceStatus


class SourceOut(CamelModel):
    """Admin view: the full record plus run stats."""

    id: uuid.UUID
    name: str
    home_url: str
    publisher: str | None
    streams: list[str]
    kind: str
    collector_type: str
    config: dict[str, Any]
    schedule: str | None
    effective_schedule: str
    rate_limit: float | None
    access_note: str | None
    status: str
    added_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    config_changed_at: datetime | None
    health: Health
    last_success_at: datetime | None
    last_run_at: datetime | None
    items_30d: int = Field(alias="items30d")
    promotion_runs: int  # qualifying runs toward the 2 needed for active


class PromotionGateOut(CamelModel):
    """Spec 4.3 step 4: runs that succeeded and found items since the config last
    changed, toward the ``needed`` (2) for promotion to active."""

    good_runs: int
    needed: int
    since: datetime | None
    met: bool


class StatusChangeOut(CamelModel):
    model_config = ConfigDict(from_attributes=True)
    at: datetime
    old_status: SourceStatus | None  # None: the source was created
    new_status: SourceStatus
    changed_by: uuid.UUID | None  # None: a system change, or a deleted account
    reason: str | None  # e.g. "config changed" (decision 27)


class SourceDetailOut(SourceOut):
    """GET /api/admin/sources/{id}: the full record, the promotion gate and the
    status history, newest first (history starts with migration 0012)."""

    promotion_gate: PromotionGateOut
    status_history: list[StatusChangeOut]


class MemberSourceOut(CamelModel):
    """Sources page (spec 4.4)."""

    id: uuid.UUID
    name: str
    home_url: str
    publisher: str | None
    kind: str
    streams: list[str]
    last_success_at: datetime | None
    items_30d: int = Field(alias="items30d")
    health: Health
    muted: bool


class RunWarningOut(CamelModel):
    """Something a run skipped without failing (decision 49). ``kind``
    ``email_no_link``: an email with no usable link; ``sender``, ``subject``
    and ``date`` (ISO when it parsed) say which. ``message`` is plain text."""

    kind: str
    message: str
    sender: str | None = None
    subject: str | None = None
    date: str | None = None


class RunOut(CamelModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    status: str
    items_found: int
    items_new: int
    items_failed: int
    error: str | None
    warnings: list[RunWarningOut] = Field(default_factory=list)

    @field_validator("warnings", mode="before")
    @classmethod
    def _known_shape(cls, v: object) -> object:
        # Stored rows are dicts; keep only the fields above (and only dicts).
        if not isinstance(v, list):
            return []
        return [w for w in v if isinstance(w, dict) and w.get("kind")]


class RunPage(CamelModel):
    total: int
    items: list[RunOut]


class PreviewItemOut(CamelModel):
    url: str
    title: str
    organisation: str | None
    listed_published: str | None
    listed_deadline: str | None
    snippet: str | None
    detail_url: str | None
    extra: dict[str, str]


class FieldErrorOut(CamelModel):
    """One refused field, for the web to show next to it. ``field`` is a dotted
    path: top-level keys camelCase (``homeUrl``), keys inside ``config`` as the
    collector names them (``config.feed_url``, ``config.selectors.item``,
    ``config.queries.0``); null when the problem is not about one field."""

    field: str | None
    message: str


class RefusalOut(CamelModel):
    """Body of a 409/422 refusal on the admin source routes: ``detail`` is the
    plain sentence(s) to show; ``errors`` the same per field."""

    detail: str
    errors: list[FieldErrorOut]


class PreviewOut(CamelModel):
    ok: bool
    # Plain sentence(s); for a config the saved source no longer passes, one per
    # field, as in ``errors``.
    error: str | None
    errors: list[FieldErrorOut]  # always sent; empty unless the config was refused
    items: list[PreviewItemOut]
    total_parsed: int
    requests_made: int
    elapsed_seconds: float
    # Emails the test run skipped for lack of a usable link (decision 49); same
    # shape as a run's warnings. Always sent, [] when none.
    warnings: list[RunWarningOut] = Field(default_factory=list)

    @field_validator("warnings", mode="before")
    @classmethod
    def _known_shape(cls, v: object) -> object:
        return RunOut._known_shape(v)


FieldKind = Literal[
    "string",
    "url",
    "integer",
    "number",
    "boolean",
    "choice",
    "string_list",
    "selector",
    "object",
    "object_list",
    "map",
    "json",
]


class ConfigFieldOut(CamelModel):
    """One config key of a collector type (``name`` is the key in ``config``)."""

    model_config = ConfigDict(from_attributes=True)
    name: str
    kind: FieldKind
    required: bool
    help: str
    default: Any = None
    options: list[str] | None = None  # kind "choice"
    min: float | None = None
    max: float | None = None
    fields: list[ConfigFieldOut] | None = None  # kinds "object", "object_list"


class CustomCollectorOut(CamelModel):
    """An allowlisted ``custom`` collector: ``name`` goes in ``config.collector``,
    ``fields`` describe ``config.options`` (same field format as above)."""

    model_config = ConfigDict(from_attributes=True)
    name: str
    help: str
    fields: list[ConfigFieldOut]


class CollectorTypeOut(CamelModel):
    """GET /api/admin/collector-types: the config form for each type (spec 4.2).
    ``schemaSource`` is always "model" now: every type's fields are read from its
    collector's config model. "declared" stays in the type for older clients."""

    model_config = ConfigDict(from_attributes=True)
    omit_if_none = frozenset({"collectors"})
    type: CollectorType
    implemented: bool
    schema_source: Literal["model", "declared"]
    fields: list[ConfigFieldOut]
    # ``custom`` only (left out for the other types): each allowlisted
    # collector with the fields of its options.
    collectors: list[CustomCollectorOut] | None = None


class SuggestionIn(CamelIn):
    model_config = ConfigDict(str_strip_whitespace=True)
    url: Annotated[str, Field(min_length=1, max_length=2048)]
    note: Annotated[str, Field(max_length=2000)] | None = None

    @field_validator("url")
    @classmethod
    def _u(cls, v):
        return _url(v)


class SuggestionOut(CamelModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    url: str
    note: str | None
    status: str
    created_at: datetime
    reviewed_at: datetime | None
    source_id: uuid.UUID | None


class AdminSuggestionOut(SuggestionOut):
    user_id: uuid.UUID
    reviewed_by: uuid.UUID | None
