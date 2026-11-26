"""Collector contract shared by every collector type (spec 4.2) and the pipeline (spec 5).

Every collector implements ``fetch(source) -> list[RawItem]``. A collector never writes to
the catalogue; the pipeline turns RawItems into opportunities.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from blackkite.db.models import Source


@dataclass(frozen=True, slots=True)
class RawItem:
    """One listing as a source showed it, before any cleaning.

    Text fields hold what the page said, verbatim. ``listed_*`` fields are strings because
    sources write dates in many forms (often without a year); the validate stage parses them.
    """

    source_id: uuid.UUID
    url: str  # link to the notice as found on the source
    title: str
    fetched_at: datetime  # timezone-aware, UTC
    organisation: str | None = None
    listed_published: str | None = None  # e.g. "9 Nov", "2026-11-09"
    listed_deadline: str | None = None  # e.g. "Closes 30 Nov 2026, 5pm"
    snippet: str | None = (
        None  # short text around the listing, for dedupe and extraction
    )
    detail_url: str | None = (
        None  # where the full notice lives, when different from url
    )
    extra: dict[str, str] = field(
        default_factory=dict
    )  # collector-specific fields (JSON-LD etc.)


# --- Procurement records (awards, plan items) ------------------------------------------
#
# Some custom collectors (umucyo_awards, umucyo_plans) collect records that are not
# opportunities. They still return ``[]`` from ``fetch`` (they never write the
# catalogue) and expose what they found as ``collector.records``: a ``Records``
# batch. The runner hands it to the matching ingest path (pipeline/awards.py,
# pipeline/plans.py); a test run previews it and writes nothing. Values are the
# text as listed; the ingest path normalises them with ``formats``.


@dataclass(frozen=True, slots=True)
class Formats:
    """How a source writes amounts and dates (from its collector config)."""

    date_formats: tuple[str, ...] = ()
    decimal_separator: str = "."
    thousands_separators: tuple[str, ...] = (",", " ")
    currency: str | None = None  # stated in the config for amounts that name none
    quarter_basis: Literal["fiscal", "calendar"] | None = None


@dataclass(frozen=True, slots=True)
class RawBidder:
    name: str | None
    price: str | None = None


@dataclass(frozen=True, slots=True)
class RawAward:
    source_id: uuid.UUID
    url: str  # the award notice, else the list page it was on
    fetched_at: datetime
    tender_ref: str | None = None
    title: str | None = None
    entity: str | None = None
    winner: str | None = None
    amount: str | None = None  # winning price as listed
    currency: str | None = None
    award_date: str | None = None
    period: str | None = None
    bidders: tuple[RawBidder, ...] = ()


@dataclass(frozen=True, slots=True)
class RawPlan:
    source_id: uuid.UUID
    url: str  # the plan entry, else the plan page it was on
    fetched_at: datetime
    entity: str | None = None
    description: str | None = None
    method: str | None = None
    estimated_value: str | None = None
    currency: str | None = None
    planned_date: str | None = None
    planned_quarter: str | None = None
    fiscal_year: str | None = None
    tender_ref: str | None = None


@dataclass(frozen=True, slots=True)
class Records:
    kind: Literal["award", "plan"]
    items: list[RawAward] | list[RawPlan]
    formats: Formats = field(default_factory=Formats)


def collected_records(collector: object) -> Records | None:
    """The procurement records the last ``fetch`` found (``collector.records``),
    or None for collectors that have none."""
    found = getattr(collector, "records", None)
    return found if isinstance(found, Records) else None


class Collector(Protocol):
    """A collector type. ``fetch`` must not raise for ordinary site failures; it raises
    ``CollectorError`` so the runner can record the failure and move on to the next source.

    Optional: ``after_commit(source) -> None``. When a collector has it, the runner
    calls it once the run's ingest is committed, and never when the ingest is rolled
    back. For side effects outside the database that must only happen when the items
    are safely stored (email_ingest flags processed mail there). A failure in it is
    logged; the run stays succeeded.

    Optional: ``warnings``, a list of dicts ``{kind, message, ...}`` for things
    the last ``fetch`` skipped without failing (email_ingest: emails with no
    usable link, decision 49). The runner stores them on the run
    (``source_run.warnings``).

    Optional: ``records``, a ``Records`` batch of awards or plan items (above)."""

    def fetch(self, source: Source) -> list[RawItem]: ...


class CollectorError(Exception):
    """A source could not be collected this run (network, parse, robots, rate limit)."""


MAX_RUN_WARNINGS = 200


def run_warnings(collector: object) -> list[dict]:
    """What the collector skipped without failing (``collector.warnings``, a
    list of dicts; decision 49), capped. Collectors without it have none."""
    found = getattr(collector, "warnings", None) or []
    return [dict(w) for w in found if isinstance(w, dict)][:MAX_RUN_WARNINGS]
