"""`bk sources`, `bk run-source`, `bk test-source` against a real database, offline web."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from typer.testing import CliRunner

from blackkite import cli
from blackkite.db.models import HttpCache, Source, SourceRun
from tests.fakes import FakeWeb, make_client

H = "notices.example"
CONFIG = {
    "list_url": f"https://{H}/tenders",
    "selectors": {"item": "li", "title": "a", "deadline": ".dl"},
}


@pytest.fixture
def bk(db_url, engine, monkeypatch, tmp_path):
    from blackkite.config import get_settings
    from blackkite.db.session import get_engine, get_sessionmaker

    web = FakeWeb()
    web.html(
        H,
        "/tenders",
        '<ul><li><a href="/n/1">Invitation for Bids</a><i class="dl">30 Nov 2026</i></li></ul>',
        etag='"abc"',
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BK_DATABASE_URL", db_url)
    for f in (get_settings, get_engine, get_sessionmaker):
        f.cache_clear()

    def fake_client(settings, sessions, *, persistent_cache):
        from blackkite.collectors.http import DbHttpCache, MemoryHttpCache

        return make_client(
            web, cache=DbHttpCache(sessions) if persistent_cache else MemoryHttpCache()
        )

    monkeypatch.setattr(cli, "_fetch_client", fake_client)
    runner = CliRunner()

    def invoke(*args):
        return runner.invoke(cli.app, list(args))

    invoke.web = web
    yield invoke
    get_engine().dispose()
    for f in (get_settings, get_engine, get_sessionmaker):
        f.cache_clear()


def add(db, name, **kw):
    s = Source(
        name=name,
        home_url=f"https://{H}",
        streams=["tender"],
        kind="original",
        collector_type=kw.pop("collector_type", "html_list"),
        config=kw.pop("config", CONFIG),
        status=kw.pop("status", "testing"),
    )
    db.add(s)
    db.commit()
    return s


def test_test_source_prints_preview_and_writes_nothing(bk, db):
    add(db, "Notices")
    r = bk("test-source", "notices")
    assert r.exit_code == 0, r.output
    assert "Notices: 1 items parsed" in r.output
    assert "Invitation for Bids" in r.output and f"https://{H}/n/1" in r.output
    assert "deadline: 30 Nov 2026" in r.output
    assert db.scalar(sa.select(sa.func.count()).select_from(SourceRun)) == 0
    assert db.scalar(sa.select(sa.func.count()).select_from(HttpCache)) == 0


def test_run_source_records_a_run_and_caches(bk, db):
    s = add(db, "Notices")
    r = bk("run-source", str(s.id))
    assert r.exit_code == 0, r.output
    assert "Notices: succeeded, found 1, new 0" in r.output
    (run,) = db.scalars(sa.select(SourceRun)).all()
    assert run.status == "succeeded" and run.items_found == 1
    assert db.get(HttpCache, f"https://{H}/tenders").etag == '"abc"'


def test_run_source_failure_exit_code(bk, db):
    add(db, "Feed", collector_type="rss", config={})
    r = bk("run-source", "Feed")
    assert r.exit_code == 1
    assert "not implemented yet" in r.output
    assert db.scalars(sa.select(SourceRun.status)).all() == ["failed"]


def test_unknown_source(bk):
    r = bk("run-source", "nope")
    assert r.exit_code == 1 and "no source 'nope'" in r.output


def test_sources_lists_status_and_health(bk, db):
    a = add(db, "Alpha", status="active")
    add(db, "Beta")
    db.add(SourceRun(source_id=a.id, status="failed"))
    db.commit()
    r = bk("sources")
    assert r.exit_code == 0, r.output
    lines = r.output.splitlines()
    assert lines[0].split()[:4] == ["name", "status", "collector", "health"]
    assert lines[1].split()[:4] == ["Alpha", "active", "html_list", "failing"]
    assert lines[2].split()[:4] == ["Beta", "testing", "html_list", "unknown"]
    assert lines[2].endswith("never")
