"""Collector contract shared by every collector type (spec 4.2) and the pipeline (spec 5).

Every collector implements ``fetch(source) -> list[RawItem]``. A collector never writes to
the catalogue; the pipeline turns RawItems into opportunities.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

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
    (``source_run.warnings``)."""

    def fetch(self, source: Source) -> list[RawItem]: ...


class CollectorError(Exception):
    """A source could not be collected this run (network, parse, robots, rate limit)."""
