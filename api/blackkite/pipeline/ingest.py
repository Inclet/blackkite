"""STUB from track A (collectors/runner). Track B's ingest replaces this file at merge.

Only the signature is the contract: the runner calls
``ingest_items(session, source, items) -> IngestResult(items_found, items_new)``.
This stub writes nothing and reports every item as found, none as new.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from blackkite.collectors.base import RawItem

if TYPE_CHECKING:
    from blackkite.db.models import Source


@dataclass(frozen=True)
class IngestResult:
    items_found: int
    items_new: int


def ingest_items(
    session: Session, source: Source, items: list[RawItem]
) -> IngestResult:
    """STUB: count only, write nothing."""
    return IngestResult(items_found=len(items), items_new=0)
