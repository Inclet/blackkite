"""Shared helpers for pipeline tests (synthetic sources and notices only)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from blackkite.collectors.base import RawItem
from blackkite.db.models import Source
from blackkite.pipeline.ingest import PipelineDeps
from blackkite.pipeline.settings import PipelineSettings
from tests.pipeline.fakes import FakeEmbedder

NOW = datetime(2026, 11, 25, 8, tzinfo=UTC)


@pytest.fixture
def make_source(db):
    def make(
        kind="original", streams=("tender",), status="active", name=None
    ) -> Source:
        s = Source(
            name=name or f"{kind}-{uuid.uuid4().hex[:6]}",
            home_url="https://example.org",
            streams=list(streams),
            kind=kind,
            collector_type="html_list",
            status=status,
        )
        db.add(s)
        db.flush()
        return s

    return make


def raw(source: Source, url: str, title: str, **kw) -> RawItem:
    return RawItem(source_id=source.id, url=url, title=title, fetched_at=NOW, **kw)


@pytest.fixture
def pipeline_settings(tmp_path) -> PipelineSettings:
    return PipelineSettings(_env_file=None, data_dir=tmp_path / "data")


@pytest.fixture
def deps(pipeline_settings):
    """No model at all: listing data only, review flags for the skipped steps."""

    def make(llm=None, embedder=None, fetcher=None) -> PipelineDeps:
        return PipelineDeps(
            fetcher=fetcher, llm=llm, embedder=embedder, settings=pipeline_settings
        )

    return make


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()
