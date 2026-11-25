"""Sandboxed test run (spec 4.3 step 2, spec 10).

Fetches once and returns the first parsed items. Writes nothing: no catalogue rows,
no source_run row, no HTTP cache row (the client gets an in-memory cache). Uses the
same URL guard as scheduled runs, preview limits (first page, first query, at most
3 detail pages), and the usual robots.txt, rate limit, size and timeout rules.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import SecretStr

from blackkite.collectors.base import CollectorError, RawItem
from blackkite.collectors.http import FetchClient
from blackkite.collectors.registry import build_collector
from blackkite.db.models import Source

log = logging.getLogger("blackkite.sources.testrun")

PREVIEW_ITEMS = 20


@dataclass
class PreviewResult:
    ok: bool
    items: list[RawItem] = field(default_factory=list)
    total_parsed: int = 0
    error: str | None = None
    requests_made: int = 0
    elapsed_seconds: float = 0.0


def transient_source(**fields: Any) -> Source:
    """A Source object that is never added to a session (for unsaved configs)."""
    fields.setdefault("id", uuid.uuid4())
    fields.setdefault("name", "(unsaved)")
    return Source(**fields)


def preview_source(
    source: Source,
    client: FetchClient,
    *,
    brave_api_key: SecretStr | None = None,
    limit: int = PREVIEW_ITEMS,
) -> PreviewResult:
    start = time.monotonic()
    try:
        collector = build_collector(
            source.collector_type, client, brave_api_key=brave_api_key, preview=True
        )
        items = collector.fetch(source)
        result = PreviewResult(ok=True, items=items[:limit], total_parsed=len(items))
    except CollectorError as e:
        result = PreviewResult(ok=False, error=str(e)[:2000])
    except Exception:  # a broken config must never 500 the admin screen
        log.exception("test run crashed for source %s", source.id)
        result = PreviewResult(ok=False, error="internal error during test run")
    finally:
        client.close()
    result.requests_made = client.requests_made
    result.elapsed_seconds = round(time.monotonic() - start, 3)
    return result
