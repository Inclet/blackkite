"""One user's scoring never reads or writes another user's rows (spec 6, 10)."""

from __future__ import annotations

import re

import sqlalchemy as sa

from blackkite.db.models import Profile, User, UserOpportunityScore, UserSourceMute
from blackkite.scoring.service import (
    backfill_profile,
    score_new_opportunities,
    score_user,
)
from blackkite.seed.loader import bootstrap
from tests.scoring.conftest import FakeScoreLLM, deps, judgement, now

COLD = "Provision of cold chain transport services for vaccines"
PER_USER = ("user_opportunity_score", "user_source_mute", "profile", "user_opportunity")


def _two_users(db, make_opp, make_source):
    a = bootstrap(db, "a@example.com").user
    b = bootstrap(db, "b@example.com").user
    b.role = "member"
    db.commit()
    shared_src = make_source()
    public = make_opp(COLD, source=shared_src, tags=["service:cold chain transport"])
    # b's private manual item and b's mute of the shared source.
    private_b = make_opp(
        COLD + " (b's own lead)",
        visibility="private",
        owner_user_id=b.id,
        source=False,
        tags=["service:cold chain transport"],
    )
    db.add(UserSourceMute(user_id=b.id, source_id=shared_src.id))
    db.commit()
    return a, b, public, private_b


def _capture(engine):
    seen: list[tuple[str, object]] = []

    def listener(conn, cursor, statement, params, context, executemany):
        seen.append((statement, params))

    sa.event.listen(engine, "before_cursor_execute", listener)
    return seen, lambda: sa.event.remove(engine, "before_cursor_execute", listener)


def _rows(db, user_id):
    db.expire_all()
    return {
        (r.opportunity_id, r.profile_id): (r.score, r.score_breakdown)
        for r in db.scalars(
            sa.select(UserOpportunityScore).where(
                UserOpportunityScore.user_id == user_id
            )
        )
    }


def test_scoring_one_user_never_reads_or_writes_another(
    db, engine, make_opp, make_source
):
    a, b, public, private_b = _two_users(db, make_opp, make_source)
    score_user(db, b.id, deps=deps(FakeScoreLLM(judgement())))
    db.commit()
    before_b = _rows(db, b.id)
    assert before_b  # b has rows of their own

    seen, stop = _capture(engine)
    try:
        score_user(db, a.id, deps=deps(FakeScoreLLM(judgement())))
        a_profile = db.scalar(
            sa.select(Profile.id).where(Profile.user_id == a.id).limit(1)
        )
        backfill_profile(db, a_profile, deps=deps(FakeScoreLLM(judgement())))
        db.commit()
    finally:
        stop()

    # Nothing of b's changed, and a never got a row for b's private item.
    assert _rows(db, b.id) == before_b
    assert all(oid != private_b.id for oid, _ in _rows(db, a.id))
    # b's mute is b's: a's Ironji row for the shared item is not filtered.
    a_ironji = db.scalar(
        sa.select(Profile.id).where(
            Profile.user_id == a.id, Profile.name == "Ironji-Trade"
        )
    )
    a_row = _rows(db, a.id)[(public.id, a_ironji)]
    assert a_row[1]["hard_filtered"] is None

    # Every statement on a per-user table carried a's id and never b's; reads of
    # scores and mutes filter on user_id in their WHERE clause.
    a_id, b_id = str(a.id), str(b.id)
    checked = 0
    for statement, params in seen:
        tables = set(re.findall(r'\b(?:FROM|JOIN|INTO|UPDATE)\s+"?(\w+)"?', statement))
        if not tables & set(PER_USER):
            continue
        checked += 1
        assert b_id not in str(params), statement
        if tables & {"user_opportunity_score", "user_source_mute"}:
            assert a_id in str(params), statement
            if statement.lstrip().upper().startswith("SELECT"):
                where = statement.split("WHERE", 1)[1]
                for t in tables & {"user_opportunity_score", "user_source_mute"}:
                    assert f"{t}.user_id = " in where, statement
    assert checked >= 4


def test_worker_trigger_keeps_users_apart(db, make_opp, make_source):
    a, b, public, private_b = _two_users(db, make_opp, make_source)
    since = now().replace(year=2000)
    score_new_opportunities(db, since, deps=deps(FakeScoreLLM(judgement())))
    db.commit()
    a_rows, b_rows = _rows(db, a.id), _rows(db, b.id)
    assert all(oid != private_b.id for oid, _ in a_rows)
    assert any(oid == private_b.id for oid, _ in b_rows)  # owner's own item is scored
    # b's mute filters b's rows only.
    b_pub = [bd for (oid, _), (_, bd) in b_rows.items() if oid == public.id]
    assert any(bd["hard_filtered"] == "muted_source_only" for bd in b_pub)
    # Every row's profile belongs to the row's user.
    owners = dict(db.execute(sa.select(Profile.id, Profile.user_id)).all())
    for r in db.scalars(sa.select(UserOpportunityScore)):
        assert owners[r.profile_id] == r.user_id
    assert db.scalar(sa.select(sa.func.count()).select_from(User)) == 2
