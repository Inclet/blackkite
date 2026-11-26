"""/profiles: the caller's own profiles, validated data, version bump, and the
backfill request (run later by the worker, never in the request)."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

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
def backfills(db, monkeypatch):
    """Profiles with a pending backfill request. Scoring in the request fails the
    test."""
    from blackkite.scoring import service

    def inline(*a, **k):
        raise AssertionError("scoring ran in the HTTP request")

    monkeypatch.setattr(service, "backfill_profile", inline)
    monkeypatch.setattr(service, "score_user", inline)

    class Pending:
        def ids(self) -> list[uuid.UUID]:
            db.expire_all()
            return list(
                db.scalars(
                    sa.select(Profile.id)
                    .where(Profile.backfill_requested_at.is_not(None))
                    .order_by(Profile.created_at)
                )
            )

        def clear(self) -> None:
            db.execute(sa.update(Profile).values(backfill_requested_at=None))
            db.commit()

        def scored(self, pid) -> None:
            """As the worker leaves it: done, up to date at this version."""
            db.execute(
                sa.update(Profile)
                .where(Profile.id == pid)
                .values(backfill_requested_at=None, scored_version=Profile.version)
            )
            db.commit()

    return Pending()


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
    assert backfills.ids() == [stored.id]
    assert stored.scored_version is None
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
    assert backfills.ids() == []


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


def test_edit_bumps_version_and_requests_a_backfill(db, client, ana, backfills):
    pid = client.post(
        "/api/profiles",
        json={"name": "Ironji-Trade", "type": "business", "data": IRONJI},
    ).json()["id"]
    backfills.scored(pid)
    r = client.patch(
        f"/api/profiles/{pid}", json={"data": {**IRONJI, "minContractRwf": 1}}
    )
    assert r.status_code == 200 and r.json()["version"] == 2
    assert backfills.ids() == [uuid.UUID(pid)]
    backfills.scored(pid)
    # No change: no new version, no backfill.
    r = client.patch(f"/api/profiles/{pid}", json={"name": "Ironji-Trade"})
    assert r.json()["version"] == 2 and backfills.ids() == []
    r = client.patch(f"/api/profiles/{pid}", json={"active": False})
    assert r.json()["version"] == 3 and r.json()["active"] is False
    assert backfills.ids() == []
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


def _edit(client, pid, **body):
    r = client.patch(f"/api/profiles/{pid}", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_rename_requests_no_backfill(db, client, ana, backfills):
    pid = client.post(
        "/api/profiles", json={"name": "A", "type": "business", "data": IRONJI}
    ).json()["id"]
    backfills.scored(pid)
    assert _edit(client, pid, name="Ironji")["version"] == 2
    assert backfills.ids() == []
    # Still up to date after a rename, and a pause asks for nothing...
    assert db.get(Profile, uuid.UUID(pid)).scored_version == 2
    _edit(client, pid, active=False)
    assert backfills.ids() == []
    # ...but reactivating catches up on items that arrived while it was off.
    _edit(client, pid, active=True)
    assert backfills.ids() == [uuid.UUID(pid)]


def test_activation_after_a_paused_edit_backfills(db, client, ana, backfills):
    pid = client.post(
        "/api/profiles", json={"name": "A", "type": "business", "data": IRONJI}
    ).json()["id"]
    backfills.scored(pid)
    _edit(client, pid, active=False)
    # Data edited while paused: nothing now (inactive profiles are not scored)...
    _edit(client, pid, data={**IRONJI, "minContractRwf": 7})
    assert backfills.ids() == []
    # ...and a backfill when it comes back.
    _edit(client, pid, active=True)
    assert backfills.ids() == [uuid.UUID(pid)]


def test_inactive_new_profile_requests_nothing(client, ana, backfills):
    r = client.post(
        "/api/profiles",
        json={"name": "A", "type": "business", "data": IRONJI, "active": False},
    )
    assert r.status_code == 201 and backfills.ids() == []
    _edit(client, r.json()["id"], active=True)  # never scored
    assert backfills.ids() == [uuid.UUID(r.json()["id"])]


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


def test_business_organisation_type_round_trips(client, ana, backfills):
    data = {**IRONJI, "organisationType": "ngo or non-profit"}
    assert validate_data("business", data)["organisation_type"] == ("ngo or non-profit")
    r = client.post(
        "/api/profiles", json={"name": "Foundation", "type": "business", "data": data}
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["organisationType"] == "ngo or non-profit"
