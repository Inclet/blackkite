"""`bk score --user` and `bk backfill --profile` against a real database."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from typer.testing import CliRunner

from blackkite import cli
from blackkite.db.models import Profile, UserOpportunityScore
from tests.scoring.conftest import ADMIN, FakeScoreLLM, deps, judgement

COLD = "Provision of cold chain transport services for vaccines"


@pytest.fixture
def bk(db_url, engine, monkeypatch, tmp_path):
    from blackkite.config import get_settings
    from blackkite.db.session import get_engine, get_sessionmaker

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BK_DATABASE_URL", db_url)
    for f in (get_settings, get_engine, get_sessionmaker):
        f.cache_clear()
    state = {"deps": deps()}
    monkeypatch.setattr(cli, "_scoring_deps", lambda: state["deps"])
    runner = CliRunner()

    def invoke(*args):
        return runner.invoke(cli.app, list(args))

    invoke.state = state
    yield invoke
    get_engine().dispose()


def _count(db, **where):
    q = sa.select(sa.func.count()).select_from(UserOpportunityScore)
    for k, v in where.items():
        q = q.where(getattr(UserOpportunityScore, k) == v)
    return db.scalar(q)


def test_score_by_email_and_id(bk, db, owner, make_opp):
    make_opp(COLD, tags=["service:cold chain transport"])
    r = bk("score", "--user", ADMIN.upper())
    assert r.exit_code == 0, r.output
    assert "ANTHROPIC_API_KEY is not set" in r.output
    assert "pairs 3" in r.output
    assert _count(db, user_id=owner.id) == 3
    bk.state["deps"] = deps(FakeScoreLLM(judgement()))
    r = bk("score", "--user", str(owner.id))
    assert r.exit_code == 0, r.output
    # Ironji shortlists the cold-chain tender; AI lab does not; Personal filters it.
    assert "model calls 1" in r.output and "not set" not in r.output


def test_score_unknown_user(bk, db):
    r = bk("score", "--user", "nobody@example.com")
    assert r.exit_code == 1 and "no user" in r.output


def test_backfill_profile(bk, db, profiles, make_opp):
    make_opp(COLD, tags=["service:cold chain transport"])
    pid = profiles["Ironji-Trade"].id
    r = bk("backfill", "--profile", str(pid))
    assert r.exit_code == 0, r.output
    assert _count(db, profile_id=pid) == 1 and _count(db) == 1
    assert bk("backfill", "--profile", str(uuid.uuid4())).exit_code == 1
    assert bk("backfill", "--profile", "not-an-id").exit_code == 1
    p = db.get(Profile, pid)
    p.active = False
    db.commit()
    r = bk("backfill", "--profile", str(pid))
    assert r.exit_code == 1 and "not active" in r.output


def _pending(db) -> set[str]:
    db.expire_all()
    return set(
        db.scalars(
            sa.select(Profile.name).where(Profile.backfill_requested_at.is_not(None))
        )
    )


def test_score_clears_the_users_pending_requests(bk, db, owner, Sessions):
    from datetime import timedelta

    from blackkite.worker.backfills import run_pending_backfills
    from tests.scoring.conftest import now

    # Bootstrap scores nothing: its profiles wait for the worker.
    assert _pending(db) == {"Ironji-Trade", "AI lab", "Personal"}
    other = Profile(user_id=_other_user(db).id, name="Theirs", type="business")
    other.backfill_requested_at = sa.func.now()
    db.add(other)
    db.commit()
    assert bk("score", "--user", ADMIN).exit_code == 0
    assert _pending(db) == {"Theirs"}  # only the scored user's profiles
    db.expire_all()
    assert all(
        p.backfill_attempts == 0
        for p in db.scalars(sa.select(Profile).where(Profile.user_id == owner.id))
    )
    later = lambda: now() + timedelta(minutes=2)
    assert run_pending_backfills(Sessions, later, deps()) == [other.id]


def test_backfill_clears_only_that_profiles_request(bk, db, profiles, make_opp):
    make_opp(COLD, tags=["service:cold chain transport"])
    pid = profiles["Ironji-Trade"].id
    assert bk("backfill", "--profile", str(pid)).exit_code == 0
    assert _pending(db) == {"AI lab", "Personal"}


def test_a_request_made_during_the_run_stays(db, profiles):
    from datetime import UTC, datetime, timedelta

    from blackkite.scoring.backfill import clear_requests

    ironji, lab = profiles["Ironji-Trade"], profiles["AI lab"]
    started = datetime.now(UTC)
    ironji.backfill_requested_at = started + timedelta(seconds=1)  # edited meanwhile
    lab.backfill_requested_at = started - timedelta(seconds=1)
    db.commit()
    assert clear_requests(db, [ironji.id, lab.id], started) == 1
    db.commit()
    assert _pending(db) == {"Ironji-Trade", "Personal"}


def _other_user(db):
    from tests.conftest import make_user

    return make_user(db, "other@example.com")
