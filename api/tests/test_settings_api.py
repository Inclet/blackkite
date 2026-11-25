"""/digest-settings (decision 18) and PATCH /me (greeting name)."""

import pytest

from blackkite.db.models import DigestSetting
from tests.conftest import make_user, sign_in


@pytest.fixture
def ana(db, client, outbox):
    u = make_user(db, "ana@example.com")
    sign_in(client, outbox, u.email)
    return u


def test_defaults_without_a_row(client, ana, db):
    assert client.get("/api/digest-settings").json() == {
        "channel": "email",
        "frequency": "weekly",
        "day": "mon",
        "alertThreshold": None,
        "streams": None,
    }
    assert db.query(DigestSetting).count() == 0


def test_put_creates_then_updates_own_row(client, ana, db):
    body = {"frequency": "off", "alertThreshold": 70, "streams": ["tender", "event"]}
    r = client.put("/api/digest-settings", json=body)
    assert r.status_code == 200
    assert r.json() == {"channel": "email", "day": "mon", **body}
    [row] = db.query(DigestSetting).all()
    assert row.user_id == ana.id and row.address == ana.email
    r = client.put("/api/digest-settings", json={"frequency": "weekly"})
    assert r.json()["alertThreshold"] is None and r.json()["streams"] is None
    assert db.query(DigestSetting).count() == 1


@pytest.mark.parametrize(
    "body",
    [
        {"frequency": "daily"},
        {"frequency": "weekly", "day": "fri"},
        {"frequency": "weekly", "channel": "telegram"},
        {"frequency": "weekly", "alertThreshold": 101},
        {"frequency": "weekly", "streams": []},
        {"frequency": "weekly", "streams": ["jobs"]},
        {"frequency": "weekly", "address": "someone@else.example"},
    ],
)
def test_put_validates(client, ana, body):
    assert client.put("/api/digest-settings", json=body).status_code == 422


def test_settings_are_per_user(client, ana, db, outbox, app):
    ben = make_user(db, "ben@example.com")
    db.add(
        DigestSetting(
            user_id=ben.id, channel="email", address=ben.email, alert_threshold=10
        )
    )
    db.commit()
    assert client.get("/api/digest-settings").json()["alertThreshold"] is None
    client.put("/api/digest-settings", json={"frequency": "off"})
    db.expire_all()
    ben_row = db.query(DigestSetting).filter_by(user_id=ben.id).one()
    assert ben_row.frequency == "weekly" and ben_row.alert_threshold == 10


def test_patch_me_sets_name(client, ana):
    r = client.patch("/api/me", json={"name": "  Ana Uwase "})
    assert r.status_code == 200 and r.json()["name"] == "Ana Uwase"
    assert client.patch("/api/me", json={"name": None}).json()["name"] is None
    assert (
        client.patch("/api/me", json={"name": "x", "role": "admin"}).status_code == 422
    )


def test_need_a_session(client):
    assert client.get("/api/digest-settings").status_code == 401
    assert (
        client.put("/api/digest-settings", json={"frequency": "off"}).status_code == 401
    )
    assert client.patch("/api/me", json={"name": "x"}).status_code == 401
