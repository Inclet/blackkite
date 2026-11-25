"""Runner and scheduler (spec 5 stage 1): source_run rows, isolation, due-ness, locks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import sqlalchemy as sa

from blackkite.db.models import Opportunity, OpportunitySource, Source, SourceRun
from blackkite.pipeline import ingest
from blackkite.worker import runner
from blackkite.worker.main import TICK_SECONDS, build_scheduler, refresh_job
from tests.fakes import FakeWeb, make_client, pipeline_deps
from tests.pipeline.fakes import FakeEmbedder, FakeLLM, q

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
        '<ul><li><a href="/n/1">Supply of school desks</a></li>'
        '<li><a href="/n/2">Supply of hospital beds</a></li></ul>',
    )
    w.html(H, "/n/1", "<p>Supply of school desks. Closing date: 10 December 2026.</p>")
    w.html(H, "/n/2", "<p>Supply of hospital beds. Closing date: 11 December 2026.</p>")
    w.add(H, "/blocked", httpx.Response(403))
    return w


@pytest.fixture
def recorded(monkeypatch):
    """Replace ingest with one that writes an opportunity per item and reports counts."""
    calls = []

    def fake_ingest(session, source, items, **kw):
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


def extraction(user: str) -> dict:
    """Fake model reply: quote the title and closing date that appear in the text."""
    title = next(
        t for t in ("Supply of school desks", "Supply of hospital beds") if t in user
    )
    day = "10" if "desks" in title else "11"
    return {
        "stream": q("tender", title),
        "title": q(title),
        "deadline_at": q(f"2026-12-{day}", f"Closing date: {day} December 2026"),
    }


def test_run_ingests_through_the_real_pipeline(db, web, tmp_path):
    s = add_source(db, "Real")
    llm, emb = FakeLLM(extraction), FakeEmbedder()
    make_deps = pipeline_deps(tmp_path / "data", llm=llm, embedder=emb)
    client = make_client(web)
    run = runner.run_source(db, s, client=client, make_deps=make_deps, now=lambda: NOW)
    assert (run.status, run.items_found, run.items_new) == ("succeeded", 2, 2)
    db.expire_all()
    opps = db.scalars(sa.select(Opportunity).order_by(Opportunity.title)).all()
    assert [(o.title, o.deadline_at.date().isoformat()) for o in opps] == [
        ("Supply of hospital beds", "2026-12-11"),
        ("Supply of school desks", "2026-12-10"),
    ]
    assert all(o.embedding is not None and not o.needs_review for o in opps)
    assert len(llm.calls) == 2
    # Detail pages were fetched through the run's own guarded client.
    assert web.paths(H) == ["/robots.txt", "/tenders", "/n/1", "/n/2"]
    assert {r.headers["user-agent"] for r in web.requests} == {client.user_agent}

    # Second run: same URLs, nothing new, no further model calls.
    again = runner.run_source(
        db, s, client=client, make_deps=make_deps, now=lambda: NOW + timedelta(hours=1)
    )
    assert (again.items_found, again.items_new) == (2, 0)
    assert db.scalar(sa.select(sa.func.count()).select_from(Opportunity)) == 2
    assert len(llm.calls) == 2


def test_detail_fetch_obeys_robots(db, web, tmp_path):
    web.add(
        H, "/robots.txt", httpx.Response(200, text="User-agent: *\nDisallow: /n/\n")
    )
    s = add_source(db, "Robots")
    llm = FakeLLM(extraction)
    run = runner.run_source(
        db,
        s,
        client=make_client(web),
        make_deps=pipeline_deps(tmp_path / "data", llm=llm, embedder=FakeEmbedder()),
        now=lambda: NOW,
    )
    assert (run.status, run.items_found, run.items_new) == ("succeeded", 2, 2)
    assert "/n/1" not in web.paths(H)
    db.expire_all()
    opp = db.scalars(sa.select(Opportunity).order_by(Opportunity.title)).first()
    assert "robots.txt disallows" in opp.evidence["_enrich"]["errors"][0]
    # The model saw only the listing text, so no deadline snippet: none was invented.
    assert opp.deadline_at is None


def test_default_deps_get_the_runs_client(db, web, monkeypatch):
    """Without make_deps the runner calls ingest.default_deps with a fetcher that
    wraps its client and the source's rate limit."""
    seen = []
    real = ingest.default_deps

    def spy(fetcher=None):
        seen.append(fetcher)
        return real(fetcher)

    monkeypatch.setattr(ingest, "default_deps", spy)
    s = add_source(db, "Defaults")
    s.rate_limit = 7.0
    db.commit()
    client = make_client(web)
    run = runner.run_source(db, s, client=client, now=lambda: NOW)
    assert run.status == "succeeded"
    [fetcher] = seen
    assert fetcher.client is client and fetcher.delay == 7.0
    assert db.scalar(sa.select(sa.func.count()).select_from(OpportunitySource)) == 2


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
    def broken(session, source, items, **kw):
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

    def ingest_or_crash(session, source, items, **kw):
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


def test_scheduler_jobs(Sessions, settings, web):
    sched = build_scheduler(Sessions, settings, client=make_client(web))
    jobs = {j.id: j for j in sched.get_jobs()}
    assert set(jobs) == {"run-due-sources", "refresh-statuses"}
    tick = jobs["run-due-sources"]
    assert tick.trigger.interval.total_seconds() == TICK_SECONDS
    assert tick.max_instances == 1 and tick.coalesce
    daily = jobs["refresh-statuses"]
    assert daily.func is refresh_job and daily.max_instances == 1 and daily.coalesce
    fire = daily.trigger.get_next_fire_time(None, NOW)
    assert (fire.hour, fire.minute) == (22, 5)  # 00:05 Africa/Kigali
    assert daily.trigger.get_next_fire_time(None, fire + timedelta(seconds=1)) == (
        fire + timedelta(days=1)
    )


def test_refresh_statuses_job_moves_items_on_under_its_lock(Sessions, db, engine):
    from blackkite.db.models import ChangeEvent

    db.add_all(
        [
            Opportunity(
                stream="tender",
                title="closes soon",
                status="open",
                deadline_at=NOW + timedelta(days=3),
            ),
            Opportunity(
                stream="tender",
                title="closed",
                status="closing_soon",
                deadline_at=NOW - timedelta(hours=1),
            ),
            Opportunity(
                stream="tender",
                title="far",
                status="open",
                deadline_at=NOW + timedelta(days=30),
            ),
        ]
    )
    db.commit()
    with runner.advisory_lock(
        engine, runner.JOB_LOCK_NAMESPACE, runner.REFRESH_STATUSES_KEY
    ) as got:
        assert got
        assert runner.refresh_statuses_locked(Sessions, now=lambda: NOW) is None
    assert runner.refresh_statuses_locked(Sessions, now=lambda: NOW) == 2
    db.expire_all()
    assert dict(db.execute(sa.select(Opportunity.title, Opportunity.status)).all()) == {
        "closes soon": "closing_soon",
        "closed": "expired",
        "far": "open",
    }
    assert db.scalar(sa.select(sa.func.count()).select_from(ChangeEvent)) == 2
    assert runner.refresh_statuses_locked(Sessions, now=lambda: NOW) == 0


def test_runs_feed_last_seen_and_items_found_in_30_days(db, web, tmp_path):
    """Spec 4.4 health: "items found in the last 30 days" counts the catalogue items
    whose opportunity_source.last_seen falls in the window, so every run must bump
    last_seen for what it saw again."""
    from blackkite.sources.service import source_stats

    s = add_source(db, "Health", created=NOW - timedelta(days=60))
    make_deps = pipeline_deps(
        tmp_path / "data", llm=FakeLLM(extraction), embedder=FakeEmbedder()
    )
    client = make_client(web)
    old = NOW - timedelta(days=40)
    runner.run_source(db, s, client=client, make_deps=make_deps, now=lambda: old)

    def stats():
        db.expire_all()
        return source_stats(db, [s.id], now=NOW)[s.id]

    links = lambda: db.scalars(sa.select(OpportunitySource)).all()
    assert {(link.first_seen, link.last_seen) for link in links()} == {(old, old)}
    assert stats().items_30d == 0 and stats().health == "ok"

    run = runner.run_source(db, s, client=client, make_deps=make_deps, now=lambda: NOW)
    assert (run.items_found, run.items_new) == (2, 0)
    assert {(link.first_seen, link.last_seen) for link in links()} == {(old, NOW)}
    st = stats()
    assert st.items_30d == 2 and st.health == "ok"
    assert st.last_success_at == NOW
