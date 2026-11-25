"""/profiles: the caller's own profiles, validated data, version bump, backfill."""

from __future__ import annotations

import uuid

import pytest

from blackkite import scoring
from blackkite.db.models import Profile, UserOpportunityScore
from blackkite.member.profiles import validate_data
from blackkite.seed.loader import load_seed_profiles
from tests import factories as f
from tests.conftest import make_user, sign_in

IRONJI = {
    "streams": ["tender", "funding", "event"],
    "location": "Kigali, Rwanda",
    "services": ["dry freight", "cold chain"],
    "registrationsHeld": ["RDB company registration"],
    "capacity": {"model": "partner network", "trucksInNetwork": 1000, "tonnage": None},
    "minContractRwf": 5000000,
}


@pytest.fixture
def backfills(monkeypatch):
    calls: list[uuid.UUID] = []
    monkeypatch.setattr(scoring, "backfill_profile", lambda s, pid: calls.append(pid))
    return calls


@pytest.fixture
def ana(db, client, outbox):
    u = make_user(db, "ana@example.com")
    sign_in(client, outbox, u.email)
    return u


def test_seed_profiles_are_valid_data():
    for entry in load_seed_profiles()["profiles"]:
        data = {k: v for k, v in entry.items() if k not in ("name", "type")}
        assert validate_data(entry["type"], data) == data


def test_create_list_and_camel_case_round_trip(db, client, ana, backfills):
    r = client.post(
        "/api/profiles",
        json={"name": "Ironji-Trade", "type": "business", "data": IRONJI},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 1 and body["active"] is True
    assert body["data"] == IRONJI
    stored = db.get(Profile, uuid.UUID(body["id"]))
    assert stored.data["capacity"] == {
        "model": "partner network",
        "trucks_in_network": 1000,
        "tonnage": None,
    }
    assert stored.data["min_contract_rwf"] == 5000000
    assert backfills == [stored.id]
    assert [p["name"] for p in client.get("/api/profiles").json()] == ["Ironji-Trade"]
    assert client.get(f"/api/profiles/{stored.id}").json()["data"] == IRONJI


@pytest.mark.parametrize(
    "data",
    [
        {},  # streams required
        {"streams": []},
        {"streams": ["jobs"]},
        {"streams": ["tender", "tender"]},
        {"streams": ["tender"], "minContractRwf": -1},
        {"streams": ["tender"], "servces": ["typo"]},
        {"streams": ["tender"], "capacity": {"fleet": 3}},
        {"streams": ["tender"], "instruments": ["bonds"]},  # personal-only key
        {"streams": ["tender"], "services": [""]},
    ],
)
def test_business_data_is_validated(client, ana, data, backfills):
    r = client.post(
        "/api/profiles", json={"name": "B", "type": "business", "data": data}
    )
    assert r.status_code == 422, r.text
    assert backfills == []


def test_personal_data_shape(client, ana, backfills):
    ok = {
        "streams": ["investment", "event"],
        "instruments": ["treasury bonds and bills"],
        "ticketRangeRwf": {"min": 100000, "max": 5000000},
        "eventTopics": ["AI and tech"],
    }
    r = client.post("/api/profiles", json={"name": "P", "type": "personal", "data": ok})
    assert r.status_code == 201 and r.json()["data"] == ok
    bad = {**ok, "ticketRangeRwf": {"min": 10, "max": 1}}
    r = client.post(
        "/api/profiles", json={"name": "Q", "type": "personal", "data": bad}
    )
    assert r.status_code == 422
    r = client.post(
        "/api/profiles",
        json={"name": "R", "type": "personal", "data": {**ok, "services": ["x"]}},
    )
    assert r.status_code == 422


def test_edit_bumps_version_and_backfills(db, client, ana, backfills):
    pid = client.post(
        "/api/profiles",
        json={"name": "Ironji-Trade", "type": "business", "data": IRONJI},
    ).json()["id"]
    backfills.clear()
    r = client.patch(
        f"/api/profiles/{pid}", json={"data": {**IRONJI, "minContractRwf": 1}}
    )
    assert r.status_code == 200 and r.json()["version"] == 2
    assert backfills == [uuid.UUID(pid)]
    # No change: no new version, no backfill.
    r = client.patch(f"/api/profiles/{pid}", json={"name": "Ironji-Trade"})
    assert r.json()["version"] == 2 and len(backfills) == 1
    r = client.patch(f"/api/profiles/{pid}", json={"active": False})
    assert r.json()["version"] == 3 and r.json()["active"] is False
    # Type change needs data for the new type.
    assert (
        client.patch(f"/api/profiles/{pid}", json={"type": "personal"}).status_code
        == 422
    )
    assert (
        client.patch(f"/api/profiles/{pid}", json={"data": {"streams": []}}).status_code
        == 422
    )


def test_names_are_unique_per_user(db, client, ana, outbox, app, backfills):
    client.post(
        "/api/profiles",
        json={"name": "A", "type": "business", "data": {"streams": ["tender"]}},
    )
    r = client.post(
        "/api/profiles",
        json={"name": "A", "type": "business", "data": {"streams": ["tender"]}},
    )
    assert r.status_code == 409
    other = make_user(db, "ben@example.com")
    f.profile(db, other, "B")
    db.commit()
    # Ana may rename to a name only Ben uses.
    pid = client.get("/api/profiles").json()[0]["id"]
    assert client.patch(f"/api/profiles/{pid}", json={"name": "B"}).status_code == 200


def test_a_failing_backfill_keeps_the_profile(client, ana, monkeypatch):
    def boom(s, pid):
        raise RuntimeError("scoring down")

    monkeypatch.setattr(scoring, "backfill_profile", boom)
    r = client.post(
        "/api/profiles",
        json={"name": "A", "type": "business", "data": {"streams": ["tender"]}},
    )
    assert r.status_code == 201
    assert client.get("/api/profiles").json()[0]["name"] == "A"


def test_other_users_profiles_are_404(db, client, ana, backfills):
    ben = make_user(db, "ben@example.com")
    theirs = f.profile(db, ben, "Ben's")
    db.commit()
    assert client.get("/api/profiles").json() == []
    assert client.get(f"/api/profiles/{theirs.id}").status_code == 404
    assert (
        client.patch(f"/api/profiles/{theirs.id}", json={"name": "x"}).status_code
        == 404
    )
    assert client.delete(f"/api/profiles/{theirs.id}").status_code == 404
    db.refresh(theirs)
    assert theirs.name == "Ben's"


def test_delete_removes_its_scores(db, client, ana, backfills):
    p = f.profile(db, ana, "A")
    src = f.source(db, "S")
    o = f.opportunity(db, "O")
    f.link(db, o, src)
    f.score(db, ana, o, p)
    db.commit()
    pid = p.id
    assert client.delete(f"/api/profiles/{pid}").status_code == 204
    db.expunge_all()
    assert db.query(UserOpportunityScore).count() == 0
    assert db.get(Profile, pid) is None


def test_profiles_need_a_session(client):
    assert client.get("/api/profiles").status_code == 401
    assert client.post("/api/profiles", json={}).status_code == 401
