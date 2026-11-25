"""Worker delivery jobs and `bk digest`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from typer.testing import CliRunner

from blackkite import cli
from blackkite.db.models import AlertLog, DigestLog, DigestSetting
from blackkite.delivery.jobs import (
    ALERTS_LOCK_KEY,
    DIGEST_LOCK_KEY,
    alerts_job,
    digest_due,
    weekly_digest_job,
)
from blackkite.delivery.mail import MemoryTransport
from blackkite.worker.runner import JOB_LOCK_NAMESPACE, advisory_lock
from tests import factories as f
from tests.conftest import TEST_UNSUBSCRIBE_SECRET, make_user
from tests.factories import KIGALI, kigali

MONDAY_7 = datetime(2026, 11, 30, 7, 0, tzinfo=KIGALI)


def _seed(db, email="ana@example.com", min_fit=None):
    u = make_user(db, email)
    db.add(
        DigestSetting(
            user_id=u.id, channel="email", address=email, alert_min_fit=min_fit
        )
    )
    src = f.source(db, f"Src {email}")
    p = f.profile(db, u, "P")
    o = f.opportunity(
        db,
        f"Tender for {email}",
        deadline_at=kigali(2026, 12, 2),
        created_at=MONDAY_7 - timedelta(hours=1),
    )
    f.link(db, o, src, f"https://example.org/{email}")
    s = f.score(db, u, o, p, 90, fit_word="strong")
    s.created_at = MONDAY_7 - timedelta(hours=1)
    db.commit()
    return u


def test_digest_due_only_monday_after_the_hour():
    assert digest_due(MONDAY_7, 7)
    assert not digest_due(MONDAY_7 - timedelta(minutes=1), 7)
    assert digest_due(MONDAY_7 + timedelta(hours=10), 7)
    assert not digest_due(MONDAY_7 + timedelta(days=1), 7)
    # 05:30 UTC on Monday is 07:30 in Kigali.
    assert digest_due(datetime(2026, 11, 30, 5, 30, tzinfo=UTC), 7)


def test_weekly_job_sends_each_user_once(Sessions, db, settings):
    _seed(db, "ana@example.com")
    _seed(db, "ben@example.com")
    off = _seed(db, "carol@example.com")
    db.execute(
        sa.update(DigestSetting)
        .where(DigestSetting.user_id == off.id)
        .values(frequency="off")
    )
    db.commit()
    out = MemoryTransport()
    assert (
        weekly_digest_job(
            Sessions, settings, out, lambda: MONDAY_7 - timedelta(hours=1)
        )
        == {}
    )
    counts = weekly_digest_job(Sessions, settings, out, lambda: MONDAY_7)
    assert counts == {"sent": 2, "off": 1}
    assert sorted(m.to for m in out.outbox) == ["ana@example.com", "ben@example.com"]
    # Each mail carries only its own user's item.
    for m in out.outbox:
        assert f"Tender for {m.to}" in m.text
        assert all(
            f"Tender for {o}" not in m.text
            for o in ("ana@example.com", "ben@example.com")
            if o != m.to
        )
    again = weekly_digest_job(
        Sessions, settings, out, lambda: MONDAY_7 + timedelta(hours=1)
    )
    assert again == {"already_sent": 2, "off": 1}
    assert len(out.outbox) == 2
    assert db.scalar(sa.select(sa.func.count()).select_from(DigestLog)) == 2


def test_jobs_skip_while_another_worker_holds_the_lock(Sessions, db, engine, settings):
    _seed(db, min_fit="good")
    out = MemoryTransport()
    with advisory_lock(engine, JOB_LOCK_NAMESPACE, DIGEST_LOCK_KEY) as got:
        assert got
        assert weekly_digest_job(Sessions, settings, out, lambda: MONDAY_7) is None
    with advisory_lock(engine, JOB_LOCK_NAMESPACE, ALERTS_LOCK_KEY) as got:
        assert alerts_job(Sessions, settings, out, lambda: MONDAY_7) is None
    assert out.outbox == []


def test_alerts_job_sends_then_nothing(Sessions, db, settings):
    _seed(db, "ana@example.com", min_fit="good")
    _seed(db, "ben@example.com", min_fit=None)
    out = MemoryTransport()
    assert alerts_job(Sessions, settings, out, lambda: MONDAY_7) == 1
    assert [m.to for m in out.outbox] == ["ana@example.com"]
    assert (
        alerts_job(Sessions, settings, out, lambda: MONDAY_7 + timedelta(hours=1)) == 0
    )
    assert db.scalar(sa.select(sa.func.count()).select_from(AlertLog)) == 1


def test_tick_runs_alerts_only_after_a_successful_run(Sessions, settings, monkeypatch):
    from blackkite.worker import main as worker_main
    from blackkite.worker.runner import RunOutcome

    calls = []
    monkeypatch.setattr(worker_main, "close_stale_runs", lambda *a: 0)
    monkeypatch.setattr(worker_main, "alerts_job", lambda *a: calls.append(a) or 0)
    outcomes = [[RunOutcome(None, "S", "failed")], [RunOutcome(None, "S", "succeeded")]]
    monkeypatch.setattr(worker_main, "run_due_sources", lambda *a, **k: outcomes.pop(0))
    out = MemoryTransport()
    worker_main.tick(Sessions, None, settings, out)
    assert calls == []
    worker_main.tick(Sessions, None, settings, out)
    assert len(calls) == 1 and calls[0][2] is out


# --- bk digest -----------------------------------------------------------------------


@pytest.fixture
def bk(db_url, engine, monkeypatch, tmp_path):
    from blackkite.config import get_settings
    from blackkite.db.session import get_engine, get_sessionmaker

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BK_DATABASE_URL", db_url)
    monkeypatch.setenv("BK_MAIL_TRANSPORT", "console")
    monkeypatch.setenv("BK_WEB_BASE_URL", "https://app.example")
    monkeypatch.setenv("BK_UNSUBSCRIBE_SECRET", TEST_UNSUBSCRIBE_SECRET)
    for fn in (get_settings, get_engine, get_sessionmaker):
        fn.cache_clear()
    runner = CliRunner()
    yield lambda *a: runner.invoke(cli.app, list(a))
    get_engine().dispose()
    for fn in (get_settings, get_engine, get_sessionmaker):
        fn.cache_clear()


def test_bk_digest_dry_run_prints_and_sends_nothing(bk, db):
    _seed(db)
    r = bk(
        "digest", "--user", "ANA@example.com", "--dry-run", "--at", MONDAY_7.isoformat()
    )
    assert r.exit_code == 0, r.output
    assert "Subject: One thing this week, one closing Wednesday" in r.output
    assert "--- text/plain ---" in r.output and "--- text/html ---" in r.output
    assert "Tender for ana@example.com" in r.output
    assert "cid:kite-logo" in r.output
    assert db.scalar(sa.select(sa.func.count()).select_from(DigestLog)) == 0


def test_bk_digest_sends_through_console_once(bk, db):
    _seed(db)
    r = bk("digest", "--user", "ana@example.com", "--at", MONDAY_7.isoformat())
    assert r.exit_code == 0, r.output
    assert "--- mail (console transport) ---" in r.output and "digest sent" in r.output
    r = bk("digest", "--user", "ana@example.com", "--at", MONDAY_7.isoformat())
    assert r.exit_code == 2 and "already sent" in r.output
    assert db.scalar(sa.select(sa.func.count()).select_from(DigestLog)) == 1


def test_bk_digest_errors(bk, db):
    make_user(db, "empty@example.com")
    assert bk("digest", "--user", "nobody@example.com", "--dry-run").exit_code == 1
    r = bk("digest", "--user", "empty@example.com", "--dry-run")
    assert r.exit_code == 2 and "nothing to send" in r.output
