"""Runner and scheduler (spec 5 stage 1): source_run rows, isolation, due-ness, locks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import sqlalchemy as sa

from blackkite.db.models import Opportunity, Source, SourceRun
from blackkite.pipeline import ingest
from blackkite.worker import runner
from blackkite.worker.main import TICK_SECONDS, build_scheduler
from tests.fakes import FakeWeb, make_client

H = "notices.example"
CONFIG = {
    "list_url": f"https://{H}/tenders",
    "selectors": {"item": "li", "title": "a"},
}
DEFAULT = "0 4 * * *"
NOW = datetime(2026, 11, 25, 9, 0, tzinfo=UTC)


def add_source(db, name, *, status="testing", config=None, schedule=None, created=None):
    s = Source(
        name=name,
        home_url=f"https://{H}",
        streams=["tender"],
        kind="original",
        collector_type="html_list",
        config=config or CONFIG,
        status=status,
        schedule=schedule,
        created_at=created or NOW - timedelta(days=2),
    )
    db.add(s)
    db.commit()
    return s


@pytest.fixture
def web():
    w = FakeWeb()
    w.html(
        H,
        "/tenders",
        '<ul><li><a href="/n/1">A</a></li><li><a href="/n/2">B</a></li></ul>',
    )
    w.add(H, "/blocked", httpx.Response(403))
    return w


@pytest.fixture
def recorded(monkeypatch):
    """Replace ingest with one that writes an opportunity per item and reports counts."""
    calls = []

    def fake_ingest(session, source, items):
        calls.append((source.name, [i.url for i in items]))
        for i in items:
            session.add(Opportunity(stream="tender", title=i.title))
        session.flush()
        return ingest.IngestResult(items_found=len(items), items_new=1)

    monkeypatch.setattr(ingest, "ingest_items", fake_ingest)
    return calls


def runs(db, source=None):
    q = sa.select(SourceRun).order_by(SourceRun.started_at)
    if source is not None:
        q = q.where(SourceRun.source_id == source.id)
    db.expire_all()
    return db.scalars(q).all()


def test_stub_ingest_counts_without_writing(db, web):
    s = add_source(db, "Stubbed")
    run = runner.run_source(db, s, client=make_client(web))
    assert (run.status, run.items_found, run.items_new) == ("succeeded", 2, 0)
    assert db.scalar(sa.select(sa.func.count()).select_from(Opportunity)) == 0


def test_successful_run_records_counts_and_commits_ingest(db, web, recorded):
    s = add_source(db, "Good")
    run = runner.run_source(db, s, client=make_client(web))
    assert run.status == "succeeded"
    assert (run.items_found, run.items_new) == (2, 1)
    assert run.started_at <= run.finished_at and run.error is None
    assert recorded == [("Good", [f"https://{H}/n/1", f"https://{H}/n/2"])]
    assert db.scalar(sa.select(sa.func.count()).select_from(Opportunity)) == 2


def test_failed_collect_marks_run_failed(db, web, recorded):
    s = add_source(db, "Blocked", config={**CONFIG, "list_url": f"https://{H}/blocked"})
    run = runner.run_source(db, s, client=make_client(web))
    assert run.status == "failed" and run.finished_at is not None
    assert run.error == f"HTTP 403 from https://{H}/blocked"
    assert recorded == []


def test_ingest_crash_rolls_back_its_writes(db, web, monkeypatch):
    def broken(session, source, items):
        session.add(Opportunity(stream="tender", title="half-written"))
        session.flush()
        raise RuntimeError("x" * 5000)

    monkeypatch.setattr(ingest, "ingest_items", broken)
    s = add_source(db, "Crashy")
    run = runner.run_source(db, s, client=make_client(web))
    assert run.status == "failed"
    assert run.error.startswith("RuntimeError: xxx")
    assert len(run.error) == runner.ERROR_MAX_CHARS and run.error.endswith(
        "[truncated]"
    )
    assert db.scalar(sa.select(sa.func.count()).select_from(Opportunity)) == 0
    assert [r.status for r in runs(db)] == ["failed"]


def test_one_failing_source_never_stops_the_others(Sessions, db, web, monkeypatch):
    real = []

    def ingest_or_crash(session, source, items):
        if source.name == "B crashes in ingest":
            raise ValueError("bad item")
        real.append(source.name)
        return ingest.IngestResult(len(items), 0)

    monkeypatch.setattr(ingest, "ingest_items", ingest_or_crash)
    add_source(db, "A blocked", config={**CONFIG, "list_url": f"https://{H}/blocked"})
    add_source(db, "B crashes in ingest")
    s = add_source(db, "C unimplemented")
    s.collector_type = "rss"
    db.commit()
    add_source(db, "D good")
    out = runner.run_due_sources(
        Sessions, client=make_client(web), default_schedule=DEFAULT, now=lambda: NOW
    )
    assert [(o.name, o.status) for o in out] == [
        ("A blocked", "failed"),
        ("B crashes in ingest", "failed"),
        ("C unimplemented", "failed"),
        ("D good", "succeeded"),
    ]
    assert real == ["D good"]
    assert "not implemented yet" in out[2].error
    assert len(runs(db)) == 4


def test_only_active_and_testing_sources_are_scheduled(Sessions, db, web):
    for status in ("suggested", "testing", "active", "paused", "retired"):
        add_source(db, status, status=status)
    out = runner.run_due_sources(
        Sessions, client=make_client(web), default_schedule=DEFAULT, now=lambda: NOW
    )
    assert sorted(o.name for o in out) == ["active", "testing"]


def test_due_rule(db):
    s = add_source(db, "Daily", created=NOW - timedelta(days=2))
    # default 04:00 UTC: never ran, created two days ago -> due
    assert runner.is_due(s, None, NOW, DEFAULT)
    # ran today at 04:00:05 -> next fire tomorrow 04:00 -> not due at 09:00
    assert not runner.is_due(s, NOW.replace(hour=4, second=5), NOW, DEFAULT)
    # ran yesterday -> today's 04:00 has passed -> due
    assert runner.is_due(s, NOW - timedelta(days=1), NOW, DEFAULT)
    # created after today's fire time -> wait for tomorrow
    fresh = add_source(db, "Fresh", created=NOW.replace(hour=8))
    assert not runner.is_due(fresh, None, NOW, DEFAULT)
    # own schedule wins over the default: every 15 minutes
    s.schedule = "*/15 * * * *"
    assert runner.is_due(s, NOW - timedelta(minutes=16), NOW, DEFAULT)
    later = NOW.replace(minute=10)
    assert not runner.is_due(s, NOW.replace(minute=1), later, DEFAULT)  # next 09:15
    s.schedule = "not cron"
    assert not runner.is_due(s, None, NOW, DEFAULT)


def test_run_due_skips_sources_not_due(Sessions, db, web):
    s = add_source(db, "Ran")
    db.add(
        SourceRun(
            source_id=s.id, status="succeeded", started_at=NOW.replace(hour=4, minute=1)
        )
    )
    db.commit()
    assert (
        runner.run_due_sources(
            Sessions, client=make_client(web), default_schedule=DEFAULT, now=lambda: NOW
        )
        == []
    )


def test_advisory_lock_stops_a_second_worker(Sessions, db, engine, web):
    s = add_source(db, "Locked")
    with runner.source_lock(engine, s.id) as got:
        assert got
        out = runner.run_source_locked(
            Sessions,
            s.id,
            client=make_client(web),
            default_schedule=DEFAULT,
            now=lambda: NOW,
        )
        assert out.status == "skipped_locked"
        with runner.source_lock(engine, s.id) as again:
            assert not again
    assert runs(db) == []
    # released: now it runs
    out = runner.run_source_locked(Sessions, s.id, client=make_client(web))
    assert out.status == "succeeded"


def test_due_rechecked_inside_the_lock(Sessions, db, web):
    """Worker 1 listed the source as due, but worker 2 ran it before 1 got the lock."""
    s = add_source(db, "Raced")
    db.add(
        SourceRun(
            source_id=s.id, status="succeeded", started_at=NOW - timedelta(minutes=1)
        )
    )
    db.commit()
    out = runner.run_source_locked(
        Sessions,
        s.id,
        client=make_client(web),
        default_schedule=DEFAULT,
        now=lambda: NOW,
    )
    assert out.status == "skipped_not_due"
    # Forced (CLI): runs regardless of schedule.
    assert runner.run_source_locked(Sessions, s.id, client=make_client(web)).status == (
        "succeeded"
    )


def test_scheduler_has_one_tick_job(Sessions, settings, web):
    sched = build_scheduler(Sessions, settings, client=make_client(web))
    (job,) = sched.get_jobs()
    assert job.id == "run-due-sources"
    assert job.trigger.interval.total_seconds() == TICK_SECONDS
    assert job.max_instances == 1 and job.coalesce
