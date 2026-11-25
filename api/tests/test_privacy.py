"""GET /me/export and DELETE /me (spec 10)."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from blackkite.db.models import (
    PER_USER_TABLES,
    AlertLog,
    DigestLog,
    DigestSetting,
    Invite,
    LoginToken,
    Opportunity,
    Source,
    SourceSuggestion,
    User,
    UserSourceMute,
)
from tests import factories as f
from tests.conftest import make_user, sign_in


def _everything(db, u, other):
    src = f.source(db, "Src")
    shared = f.opportunity(db, "Shared tender")
    f.link(db, shared, src)
    mine = f.opportunity(
        db, "My land offer", visibility="private", owner_user_id=u.id, value_note="ask"
    )
    theirs = f.opportunity(
        db, "Their item", visibility="private", owner_user_id=other.id
    )
    p = f.profile(db, u, "Ironji-Trade", min_contract_rwf=5000000)
    f.score(db, u, shared, p, 80)
    f.state(db, u, shared, "saved", note="call them")
    f.state(db, other, shared, "dismissed", note="other's note")
    db.add(
        DigestSetting(
            user_id=u.id, channel="email", address=u.email, alert_threshold=60
        )
    )
    db.add(DigestLog(user_id=u.id, opportunity_ids=[shared.id], details={"items": []}))
    db.add(AlertLog(user_id=u.id, opportunity_id=shared.id))
    db.add(SourceSuggestion(user_id=u.id, url="https://new.example", note="good"))
    db.add(UserSourceMute(user_id=u.id, source_id=src.id))
    src.added_by = u.id
    db.add(
        Invite(
            email=u.email.upper(),
            token_hash="h" * 64,
            expires_at=f.NOW,
            invited_by=other.id,
        )
    )
    db.commit()
    return shared, mine, theirs


@pytest.fixture
def pair(db, client, outbox):
    u = make_user(db, "ana@example.com")
    u.name = "Ana"
    other = make_user(db, "admin@example.com", role="admin")
    db.commit()
    sign_in(client, outbox, u.email)
    return u, other


def test_export_has_only_the_callers_data(db, client, pair):
    u, other = pair
    shared, _mine, _theirs = _everything(db, u, other)
    r = client.get("/me/export")
    assert r.status_code == 200
    body = r.json()
    assert body["account"]["email"] == "ana@example.com"
    assert [p["name"] for p in body["profiles"]] == ["Ironji-Trade"]
    assert body["profiles"][0]["data"]["minContractRwf"] == 5000000
    assert body["digestSettings"][0]["alertThreshold"] == 60
    assert body["states"] == [
        {
            "opportunityId": str(shared.id),
            "title": "Shared tender",
            "state": "saved",
            "dismissReason": None,
            "note": "call them",
            "updatedAt": body["states"][0]["updatedAt"],
        }
    ]
    assert [i["title"] for i in body["privateItems"]] == ["My land offer"]
    assert body["privateItems"][0]["valueNote"] == "ask"
    assert body["digestLog"][0]["opportunityIds"] == [str(shared.id)]
    assert body["alertLog"][0]["opportunityId"] == str(shared.id)
    assert body["sourceSuggestions"][0]["url"] == "https://new.example"
    assert body["mutedSources"][0]["name"] == "Src"
    assert "other's note" not in r.text and "Their item" not in r.text
    assert "admin@example.com" not in r.text
    assert '"score"' not in r.text


def test_delete_removes_every_per_user_row_and_own_private_items(
    db, client, pair, engine
):
    u, other = pair
    shared, mine, theirs = _everything(db, u, other)
    uid, shared_id, mine_id, theirs_id = u.id, shared.id, mine.id, theirs.id
    r = client.delete("/me")
    assert r.status_code == 204
    assert "bk_session=" in r.headers["set-cookie"]
    assert client.get("/feed").status_code == 401
    db.expunge_all()
    with engine.connect() as c:
        for table in PER_USER_TABLES:
            n = c.scalar(
                sa.text(f'SELECT count(*) FROM "{table}" WHERE user_id = :u'),
                {"u": uid},
            )
            assert n == 0, table
    assert db.get(User, uid) is None
    assert (
        db.scalar(
            sa.select(sa.func.count())
            .select_from(LoginToken)
            .where(LoginToken.user_id == uid)
        )
        == 0
    )
    assert db.scalar(sa.select(sa.func.count()).select_from(Invite)) == 0
    assert db.get(Opportunity, mine_id) is None
    assert db.get(Opportunity, shared_id) is not None
    assert db.get(Opportunity, theirs_id) is not None
    src = db.scalar(sa.select(Source))
    assert src is not None and src.added_by is None
    # The other user's rows are untouched.
    assert (
        db.scalar(
            sa.text("SELECT count(*) FROM user_opportunity WHERE user_id = :u"),
            {"u": other.id},
        )
        == 1
    )


def test_last_admin_cannot_delete_themselves(db, client, outbox):
    make_user(db, "boss@example.com", role="admin")
    make_user(db, "old@example.com", role="admin", status="deactivated")
    sign_in(client, outbox, "boss@example.com")
    r = client.delete("/me")
    assert r.status_code == 409
    assert client.get("/me").status_code == 200


def test_need_a_session(client):
    assert client.get("/me/export").status_code == 401
    assert client.delete("/me").status_code == 401
