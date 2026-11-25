"""Member API response and request models (docs/api-contract.md section 2).

JSON is camelCase. ``FeedItem`` and ``FeedContent`` match
``web/src/fixtures/types.ts`` field for field: optional TypeScript fields
(``organisationShort?: string``) are left out of the JSON when empty rather than
sent as ``null``; fields typed ``| null`` (``fit``, ``deadline``) are always sent.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer
from pydantic.alias_generators import to_camel

Stream = Literal["tender", "investment", "funding", "event"]
Fit = Literal["strong", "good", "possible", "not-scored"]
TrustState = Literal["confirmed", "unconfirmed", "conflict"]
State = Literal["unseen", "saved", "dismissed", "acting", "done"]
NoDeadlineText = Literal["No deadline", "No deadline stated"]


class CamelModel(BaseModel):
    """camelCase JSON. Fields named in ``omit_if_none`` are dropped when None."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True
    )
    omit_if_none: ClassVar[frozenset[str]] = frozenset()

    @model_serializer(mode="wrap")
    def _drop_empty_optionals(self, handler: Any) -> Any:
        data = handler(self)
        if isinstance(data, dict):
            for name in self.omit_if_none:
                for key in (name, to_camel(name)):
                    if key in data and data[key] is None:
                        del data[key]
        return data


class CamelIn(BaseModel):
    """Request bodies: camelCase keys (snake_case also accepted); unknown keys
    are an error."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid"
    )


# --- feed ----------------------------------------------------------------------------


class EventDates(CamelModel):
    omit_if_none = frozenset({"end"})

    start: str
    end: str | None = None


class Trust(CamelModel):
    state: TrustState
    desktop: str
    phone: str


class FeedItemDetail(CamelModel):
    omit_if_none = frozenset({"profile", "location", "to_check"})

    profile: str | None = None
    location: str | None = None
    reasons: list[str]
    to_check: str | None = None
    trust: Trust
    original_url: str


class FeedItem(CamelModel):
    omit_if_none = frozenset(
        {
            "organisation_short",
            "top_flag",
            "topic",
            "venue",
            "note",
            "event_dates",
            "no_deadline_text",
            "hide_on_phone",
            "is_new",
        }
    )

    id: str
    stream: Stream
    # The caller's state for the item (decision 19), always sent (contract
    # section 2); also in OpportunityDetail.state.
    state: State
    title: str
    organisation: str
    organisation_short: str | None = None
    fit: Fit | None
    top_flag: str | None = None
    topic: str | None = None
    venue: str | None = None
    note: str | None = None
    deadline: str | None
    event_dates: EventDates | None = None
    no_deadline_text: NoDeadlineText | None = None
    hide_on_phone: bool | None = None
    is_new: bool | None = None
    detail: FeedItemDetail


class FeedUser(CamelModel):
    name: str


class FeedSources(CamelModel):
    checked: int
    when: str


class FeedDigest(CamelModel):
    channel: str


class FeedContent(CamelModel):
    user: FeedUser
    sources: FeedSources
    digest: FeedDigest
    items: list[FeedItem]


# --- opportunity page ----------------------------------------------------------------


class FieldOut(CamelModel):
    """One extracted field with the passage that supports it."""

    omit_if_none = frozenset({"snippet", "snippets"})

    name: str
    value: Any
    snippet: str | None = None
    snippets: list[str] | None = None


class SourceLinkOut(CamelModel):
    name: str
    url: str
    is_original: bool
    first_seen: datetime
    last_seen: datetime


class DocumentOut(CamelModel):
    name: str


class ChangeOut(CamelModel):
    field: str
    old: Any
    new: Any
    at: datetime


class OpportunityDetail(FeedItemDetail):
    omit_if_none = FeedItemDetail.omit_if_none | {"dismiss_reason"}

    fields: list[FieldOut]
    sources: list[SourceLinkOut]
    documents: list[DocumentOut]
    changes: list[ChangeOut]
    note: str | None
    # The caller's state for this item (decision 19); same as FeedItem.state.
    state: State
    dismiss_reason: str | None = None


class OpportunityOut(FeedItem):
    detail: OpportunityDetail  # type: ignore[assignment]


# --- actions -------------------------------------------------------------------------


class StateIn(CamelIn):
    state: State
    dismiss_reason: str | None = Field(default=None, max_length=500)


class NoteIn(CamelIn):
    note: str | None = Field(default=None, max_length=5000)


class UserStateOut(CamelModel):
    opportunity_id: str
    state: State
    dismiss_reason: str | None
    note: str | None
    updated_at: datetime | None
