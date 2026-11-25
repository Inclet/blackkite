"""Profile backfills off the request path (spec 5 cost guard): requests recorded
by the API, run by the worker after a debounce under a per-profile lock; model
judgements reused while the profile's scoring-relevant content is unchanged."""

from __future__ import annotations

from datetime import timedelta

import sqlalchemy as sa

from blackkite.db.models import Profile, UserOpportunityScore
from blackkite.member import profiles as P
from blackkite.scoring.backfill import BACKFILL_DEBOUNCE
from blackkite.scoring.service import backfill_profile, profile_hash
from blackkite.worker import backfills as W
from blackkite.worker.runner import advisory_lock
from tests.conftest import sign_in
from tests.scoring.conftest import (
    ADMIN,
    FakeScoreLLM,
    deps,
    judgement,
    now,
    row,
)

COLD = "Provision of cold chain transport services for vaccines"


def _cold(make_opp):
    return make_opp(
        COLD,
        tags=["service:cold chain transport"],
        value_amount=9e6,
        value_currency="RWF",
    )


def _pending(db) -> dict[str, object]:
    db.expire_all()
    return {
        p.name: p.backfill_requested_at
        for p in db.scalars(
            sa.select(Profile).where(Profile.backfill_requested_at.is_not(None))
        )
    }


def _only(db, profiles, name, at):
    """Leave one pending request, for ``name``, stamped ``at``."""
    db.execute(sa.update(Profile).values(backfill_requested_at=None))
    db.execute(
        sa.update(Profile)
        .where(Profile.id == profiles[name].id)
        .values(backfill_requested_at=at)
    )
    db.commit()


def _scores(db, profile) -> int:
    return db.scalar(
        sa.select(sa.func.count())
        .select_from(UserOpportunityScore)
        .where(
            UserOpportunityScore.user_id == profile.user_id,
            UserOpportunityScore.profile_id == profile.id,
        )
    )


# --- reuse keyed on content, not updated_at ------------------------------------------


def test_rename_keeps_the_judgement_a_data_edit_does_not(db, owner, profiles, make_opp):
    o = _cold(make_opp)
    ironji = profiles["Ironji-Trade"]
    backfill_profile(db, ironji.id, deps=deps(FakeScoreLLM(judgement())))
    db.commit()
    assert row(db, ironji, o).profile_hash == profile_hash(ironji)

    ironji = db.get(Profile, ironji.id)
    P.update_profile(db, owner, ironji, P.ProfilePatch(name="Ironji"))
    assert ironji.updated_at > row(db, ironji, o).created_at
    llm = FakeScoreLLM(judgement())
    stats = backfill_profile(db, ironji.id, deps=deps(llm), now=now())
    db.commit()
    assert llm.calls == [] and stats.llm_reused == 1

    data = {**ironji.data, "services": [*ironji.data["services"], "warehousing"]}
    P.update_profile(db, owner, ironji, P.ProfilePatch(data=data))
    llm = FakeScoreLLM(judgement(fit=0.6))
    backfill_profile(db, ironji.id, deps=deps(llm), now=now())
    db.commit()
    assert len(llm.calls) == 1
    assert row(db, ironji, o).profile_hash == profile_hash(ironji)


def test_rows_without_a_hash_fall_back_to_updated_at(db, profiles, make_opp):
    o = _cold(make_opp)
    ironji = profiles["Ironji-Trade"]
    backfill_profile(db, ironji.id, deps=deps(FakeScoreLLM(judgement())))
    db.execute(sa.update(UserOpportunityScore).values(profile_hash=None))
    db.commit()
    llm = FakeScoreLLM(judgement())
    stats = backfill_profile(db, ironji.id, deps=deps(llm), now=now())
    db.commit()
    assert llm.calls == [] and stats.llm_reused == 1
    assert row(db, ironji, o).profile_hash == profile_hash(ironji)  # backfilled


def test_profile_hash_ignores_name_and_active(profiles):
    p = profiles["Ironji-Trade"]
    h = profile_hash(p)
    p.name, p.active, p.version = "Other", False, 9
    assert profile_hash(p) == h
    p.data = {**p.data, "streams": ["tender"]}
    assert profile_hash(p) != h


# --- the worker -------------------------------------------------------------------------


def test_debounced_then_run_once_and_marked_scored(db, Sessions, profiles, make_opp):
    _cold(make_opp)
    ironji = profiles["Ironji-Trade"]
    t0 = now()
    _only(db, profiles, "Ironji-Trade", t0)
    assert W.run_pending_backfills(Sessions, lambda: t0 + timedelta(seconds=30)) == []
    assert _scores(db, ironji) == 0 and "Ironji-Trade" in _pending(db)

    # A newer edit restarts the wait.
    _only(db, profiles, "Ironji-Trade", t0 + timedelta(seconds=40))
    assert W.run_pending_backfills(Sessions, lambda: t0 + timedelta(seconds=70)) == []

    at = t0 + timedelta(seconds=40) + BACKFILL_DEBOUNCE
    assert W.run_pending_backfills(Sessions, lambda: at) == [ironji.id]
    assert _scores(db, ironji) == 1 and _pending(db) == {}
    db.expire_all()
    p = db.get(Profile, ironji.id)
    assert p.scored_version == p.version
    # Nothing pending: the next tick does nothing.
    assert W.run_pending_backfills(Sessions, lambda: at + timedelta(minutes=5)) == []


def test_edit_during_the_run_keeps_the_request(
    db, Sessions, profiles, make_opp, monkeypatch
):
    from blackkite.scoring import service

    _cold(make_opp)
    ironji = profiles["Ironji-Trade"]
    t0 = now() - timedelta(minutes=5)
    _only(db, profiles, "Ironji-Trade", t0)
    real = service.backfill_profile
    edited_at = now()

    def edit_meanwhile(session, pid, **kw):
        # The owner saves an edit after the worker picked the request up.
        with Sessions() as other:
            p = other.get(Profile, pid)
            p.data = {**p.data, "services": ["dry freight"]}
            p.version += 1
            p.backfill_requested_at = edited_at
            other.commit()
        return real(session, pid, **kw)

    monkeypatch.setattr(service, "backfill_profile", edit_meanwhile)
    assert W.run_pending_backfills(Sessions, now) == [ironji.id]
    db.expire_all()
    p = db.get(Profile, ironji.id)
    assert p.backfill_requested_at == edited_at  # runs again later
    assert p.scored_version != p.version  # the edit is not yet scored


def test_locked_profile_is_skipped(db, Sessions, engine, profiles, make_opp):
    _cold(make_opp)
    ironji = profiles["Ironji-Trade"]
    _only(db, profiles, "Ironji-Trade", now() - timedelta(minutes=5))
    key = W.profile_lock_key(ironji.id)
    with advisory_lock(engine, W.PROFILE_LOCK_NAMESPACE, key) as got:
        assert got
        assert W.run_pending_backfills(Sessions) == []
    assert _scores(db, ironji) == 0 and "Ironji-Trade" in _pending(db)
    assert W.run_pending_backfills(Sessions) == [ironji.id]


def test_inactive_profile_request_is_cleared_without_scoring(
    db, Sessions, profiles, make_opp
):
    _cold(make_opp)
    ironji = profiles["Ironji-Trade"]
    _only(db, profiles, "Ironji-Trade", now() - timedelta(minutes=5))
    db.execute(sa.update(Profile).where(Profile.id == ironji.id).values(active=False))
    db.commit()
    assert W.run_pending_backfills(Sessions) == []
    assert _scores(db, ironji) == 0 and _pending(db) == {}


def test_a_failure_is_pushed_back_and_others_still_run(
    db, Sessions, profiles, make_opp, monkeypatch, caplog
):
    from blackkite.scoring import service

    _cold(make_opp)
    ironji, lab = profiles["Ironji-Trade"], profiles["AI lab"]
    old = now() - timedelta(minutes=5)
    db.execute(sa.update(Profile).values(backfill_requested_at=None))
    db.execute(
        sa.update(Profile)
        .where(Profile.id.in_([ironji.id, lab.id]))
        .values(backfill_requested_at=old)
    )
    db.commit()
    real = service.backfill_profile

    def flaky(session, pid, **kw):
        if pid == ironji.id:
            raise RuntimeError("scoring down")
        return real(session, pid, **kw)

    monkeypatch.setattr(service, "backfill_profile", flaky)
    at = now()
    with caplog.at_level("ERROR", logger="blackkite.worker"):
        assert W.run_pending_backfills(Sessions, lambda: at) == [lab.id]
    assert "backfill failed for profile" in caplog.text
    assert _pending(db) == {"Ironji-Trade": at}  # retried after another debounce
    monkeypatch.setattr(service, "backfill_profile", real)
    assert W.run_pending_backfills(Sessions, lambda: at + BACKFILL_DEBOUNCE) == [
        ironji.id
    ]


def test_profile_api_scores_only_through_the_worker(
    db, client, outbox, Sessions, owner, make_opp, monkeypatch
):
    """POST /profiles answers without scoring; the worker's next tick does it."""
    from blackkite.scoring import service

    _cold(make_opp)
    db.execute(sa.update(Profile).values(backfill_requested_at=None))
    db.commit()
    sign_in(client, outbox, ADMIN)
    real = service.backfill_profile
    calls = []

    def inline_guard(session, pid, **kw):
        calls.append(pid)
        return real(session, pid, **kw)

    monkeypatch.setattr(service, "backfill_profile", inline_guard)
    r = client.post(
        "/api/profiles",
        json={
            "name": "Cold",
            "type": "business",
            "data": {"streams": ["tender"], "services": ["cold chain transport"]},
        },
    )
    assert r.status_code == 201 and calls == []
    p = db.get(Profile, r.json()["id"])
    assert _scores(db, p) == 0
    later = lambda: now() + BACKFILL_DEBOUNCE + timedelta(seconds=1)
    assert W.run_pending_backfills(Sessions, later) == [p.id]
    assert calls == [p.id] and _scores(db, p) == 1


def test_tick_runs_backfills_then_alerts(Sessions, settings, monkeypatch):
    from blackkite.delivery.mail import MemoryTransport
    from blackkite.worker import main as worker_main

    alerts = []
    monkeypatch.setattr(worker_main, "close_stale_runs", lambda *a: 0)
    monkeypatch.setattr(worker_main, "run_due_sources", lambda *a, **k: [])
    monkeypatch.setattr(worker_main, "alerts_job", lambda *a: alerts.append(a) or 0)
    ran = [[], ["pid"]]
    monkeypatch.setattr(worker_main, "run_pending_backfills", lambda s: ran.pop(0))
    out = MemoryTransport()
    worker_main.tick(Sessions, None, settings, out)
    assert alerts == []
    worker_main.tick(Sessions, None, settings, out)
    assert len(alerts) == 1
