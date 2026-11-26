"""Sandboxed test run (spec 4.3 step 2, spec 10).

Fetches once and returns the first parsed items. Writes nothing: no catalogue rows,
no source_run row, no HTTP cache row (the client gets an in-memory cache). Uses the
same URL guard as scheduled runs, preview limits (first page, first query, at most
3 detail pages), and the usual robots.txt, rate limit, size and timeout rules.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from pydantic import SecretStr

from blackkite.collectors.base import CollectorError, RawItem, run_warnings
from blackkite.collectors.http import FetchClient
from blackkite.collectors.problems import ConfigInvalid, Problem
from blackkite.collectors.registry import build_collector
from blackkite.db.models import Source

log = logging.getLogger("blackkite.sources.testrun")

TEST_RUN_BUSY = "Another test run is in progress; try again in a minute."


class TestRunBusy(Exception):
    """Every test-run slot is taken."""

    __test__ = False  # not a pytest class


class TestRunGate:
    """Caps the test runs in flight in this process (``BK_TEST_RUNS_MAX_CONCURRENT``).
    Every collector type takes a slot, browser_list (headless Chromium) included.
    Never waits: when all slots are taken, ``slot()`` raises ``TestRunBusy``."""

    __test__ = False  # not a pytest class

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._sem = threading.BoundedSemaphore(limit)

    @contextmanager
    def slot(self) -> Iterator[None]:
        if not self._sem.acquire(blocking=False):
            raise TestRunBusy(TEST_RUN_BUSY)
        try:
            yield
        finally:
            self._sem.release()


PREVIEW_ITEMS = 20


@dataclass
class PreviewResult:
    ok: bool
    items: list[RawItem] = field(default_factory=list)
    total_parsed: int = 0
    error: str | None = None
    requests_made: int = 0
    elapsed_seconds: float = 0.0
    # Field problems when the config itself was refused (nothing was fetched).
    problems: list[Problem] = field(default_factory=list)
    # What the fetch skipped without failing (decision 49), as on a run.
    warnings: list[dict] = field(default_factory=list)


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
        result = PreviewResult(
            ok=True,
            items=items[:limit],
            total_parsed=len(items),
            warnings=run_warnings(collector),
        )
    except ConfigInvalid as e:
        result = PreviewResult(ok=False, error=e.text[:2000], problems=e.problems)
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
