"""Roles (spec 3), invites, deactivation."""

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from blackkite.db.models import Invite, LoginToken, Session, User
from tests.conftest import make_user, sign_in, token_from_mail, verify

ADMIN = "admin@example.com"
MEMBER = "member@example.com"


def _admin_route_templates(app) -> set[tuple[str, str]]:
    """Every (method, path) under /api/admin, from the OpenAPI schema
    (test_every_admin_route_is_in_openapi checks none is hidden from it)."""
    return {
        (method.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        if path.startswith("/api/admin")
        for method in ops
    }


def _admin_routes(app):
    for method, path in sorted(_admin_route_templates(app)):
        yield method, re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), path)


@pytest.fixture
def admin_client(client, db, outbox):
    make_user(db, ADMIN, role="admin")
    return sign_in(client, outbox, ADMIN)


def _new_client(app):
    return TestClient(app, base_url="https://testserver")


def test_admin_routes_exist(app):
    assert _admin_route_templates(app) == {
        ("POST", "/api/admin/invites"),
        ("GET", "/api/admin/invites"),
        ("DELETE", "/api/admin/invites/{invite_id}"),
        ("GET", "/api/admin/users"),
        ("POST", "/api/admin/users/{user_id}/deactivate"),
        ("PATCH", "/api/admin/users/{user_id}"),
        ("GET", "/api/admin/sources"),
        ("POST", "/api/admin/sources"),
        ("GET", "/api/admin/sources/{source_id}"),
        ("PATCH", "/api/admin/sources/{source_id}"),
        ("POST", "/api/admin/sources/{source_id}/status"),
        ("GET", "/api/admin/sources/{source_id}/runs"),
        ("POST", "/api/admin/sources/test-run"),
        ("POST", "/api/admin/sources/{source_id}/test-run"),
        ("GET", "/api/admin/collector-types"),
        ("GET", "/api/admin/source-suggestions"),
        ("POST", "/api/admin/source-suggestions/{suggestion_id}/accept"),
        ("POST", "/api/admin/source-suggestions/{suggestion_id}/reject"),
        ("GET", "/api/admin/catalogue"),
        ("POST", "/api/admin/catalogue/{opportunity_id}/review"),
        ("POST", "/api/admin/catalogue/{opportunity_id}/publish"),
    }


def test_every_admin_route_is_in_openapi(app):
    """The 401/403 checks below enumerate routes from OpenAPI, so no route under
    /api/admin may be hidden from it."""
    from fastapi.routing import APIRoute

    from blackkite.routes import admin, catalogue, sources

    served = {
        (m, "/api" + r.path)
        for router in (admin.router, sources.admin_router, catalogue.router)
        for r in router.routes
        if isinstance(r, APIRoute)
        for m in r.methods
    }
    assert served == _admin_route_templates(app)


def test_old_admin_api_paths_are_gone(app, admin_client):
    """docs/api-contract.md section 2 (M3): /admin/* are web screens now; no API
    route is served there, not even to an admin."""
    assert not [p for p in app.openapi()["paths"] if p.startswith("/admin")]
    for method, path in _admin_routes(app):
        old = path.removeprefix("/api")
        r = admin_client.request(method, old, json={"email": "x@example.com"})
        assert r.status_code in (404, 405), (method, old, r.status_code)
    assert admin_client.get("/admin/users").status_code == 404
    assert admin_client.get("/api/admin/users").status_code == 200


def test_unauthenticated_gets_401_on_every_admin_route(app):
    c = _new_client(app)
    routes = list(_admin_routes(app))
    assert routes
    for method, path in routes:
        r = c.request(method, path, json={"email": "x@example.com"})
        assert r.status_code == 401, (method, path)


def test_member_gets_403_on_every_admin_route(app, db, outbox):
    make_user(db, MEMBER)
    c = sign_in(_new_client(app), outbox, MEMBER)
    for method, path in _admin_routes(app):
        r = c.request(method, path, json={"email": "x@example.com"})
        assert r.status_code == 403, (method, path)
    assert db.scalar(sa.select(sa.func.count()).select_from(Invite)) == 0


def test_invite_accept_via_invite_link(app, admin_client, db, outbox):
    r = admin_client.post("/api/admin/invites", json={"email": "New@Example.com"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "new@example.com" and body["status"] == "pending"
    mail = outbox.outbox[-1]
    assert mail.to == "new@example.com"
    token = token_from_mail(mail.text)

    invitee = _new_client(app)
    r = verify(invitee, token)
    assert r.status_code == 200
    me = invitee.get("/me").json()
    assert me["email"] == "new@example.com" and me["role"] == "member"

    invite = db.scalar(sa.select(Invite))
    assert invite.accepted_at is not None
    assert str(invite.accepted_user_id) == me["id"]
    assert admin_client.get("/api/admin/invites").json()[0]["status"] == "accepted"
    # The invite link works once.
    again = verify(_new_client(app), token)
    assert again.status_code == 400
    assert db.scalar(sa.select(sa.func.count()).select_from(User)) == 2


def test_invite_holder_can_request_a_link(app, admin_client, db, outbox):
    admin_client.post("/api/admin/invites", json={"email": "new@example.com"})
    invitee = sign_in(_new_client(app), outbox, "new@example.com")
    assert invitee.get("/me").json()["role"] == "member"
    assert db.scalar(sa.select(Invite.accepted_at)) is not None


def test_expired_invite_cannot_sign_in(app, admin_client, db, outbox):
    admin_client.post("/api/admin/invites", json={"email": "new@example.com"})
    token = token_from_mail(outbox.outbox[-1].text)
    db.execute(
        sa.update(Invite).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db.commit()
    n = len(outbox.outbox)
    c = _new_client(app)
    assert (
        c.post("/auth/request-link", json={"email": "new@example.com"}).status_code
        == 202
    )
    assert len(outbox.outbox) == n  # no link for an expired invite
    assert verify(c, token).status_code == 400
    assert admin_client.get("/api/admin/invites").json()[0]["status"] == "expired"


def test_deleted_invite_link_stops_working(app, admin_client, db, outbox):
    invite_id = admin_client.post(
        "/api/admin/invites", json={"email": "new@example.com"}
    ).json()["id"]
    token = token_from_mail(outbox.outbox[-1].text)
    assert admin_client.delete(f"/api/admin/invites/{invite_id}").status_code == 204
    assert admin_client.delete(f"/api/admin/invites/{invite_id}").status_code == 404
    r = verify(_new_client(app), token)
    assert r.status_code == 400


def test_cannot_delete_accepted_invite(app, admin_client, outbox):
    invite_id = admin_client.post(
        "/api/admin/invites", json={"email": "new@example.com"}
    ).json()["id"]
    sign_in(_new_client(app), outbox, "new@example.com")
    assert admin_client.delete(f"/api/admin/invites/{invite_id}").status_code == 409


def test_cannot_invite_existing_user(admin_client, db):
    make_user(db, MEMBER)
    assert (
        admin_client.post(
            "/api/admin/invites", json={"email": MEMBER.upper()}
        ).status_code
        == 409
    )


def test_reinvite_replaces_pending_invite(admin_client, db, outbox):
    admin_client.post("/api/admin/invites", json={"email": "new@example.com"})
    old = token_from_mail(outbox.outbox[-1].text)
    admin_client.post("/api/admin/invites", json={"email": "new@example.com"})
    assert db.scalar(sa.select(sa.func.count()).select_from(Invite)) == 1
    c = TestClient(admin_client.app, base_url="https://testserver")
    assert verify(c, old).status_code == 400


def test_list_users(admin_client, db):
    make_user(db, MEMBER)
    users = admin_client.get("/api/admin/users").json()
    assert [u["email"] for u in users] == [ADMIN, MEMBER]
    assert set(users[0]) == {
        "id",
        "email",
        "name",
        "role",
        "status",
        "createdAt",
        "lastSignInAt",
    }
    assert [(u["role"], u["status"]) for u in users] == [
        ("admin", "active"),
        ("member", "active"),
    ]
    # The admin signed in (fixture); the member never has.
    assert users[0]["lastSignInAt"] is not None
    assert users[1]["lastSignInAt"] is None


def test_last_sign_in_moves_on_each_sign_in(app, admin_client, db, outbox):
    member = make_user(db, MEMBER)
    sign_in(_new_client(app), outbox, MEMBER)
    db.refresh(member)
    first = member.last_sign_in_at
    assert first is not None
    sign_in(_new_client(app), outbox, MEMBER)
    db.refresh(member)
    assert member.last_sign_in_at > first
    row = [
        u for u in admin_client.get("/api/admin/users").json() if u["email"] == MEMBER
    ]
    assert row[0]["lastSignInAt"] is not None


def test_invites_list_filters_by_status(app, admin_client, db, outbox):
    for e in ("a@example.com", "b@example.com", "c@example.com"):
        admin_client.post("/api/admin/invites", json={"email": e})
    sign_in(_new_client(app), outbox, "a@example.com")
    db.execute(
        sa.update(Invite)
        .where(Invite.email == "b@example.com")
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db.commit()
    url = "/api/admin/invites"
    assert {i["email"]: i["status"] for i in admin_client.get(url).json()} == {
        "a@example.com": "accepted",
        "b@example.com": "expired",
        "c@example.com": "pending",
    }
    for status, email in [
        ("accepted", "a@example.com"),
        ("expired", "b@example.com"),
        ("pending", "c@example.com"),
    ]:
        got = admin_client.get(url, params={"status": status}).json()
        assert [i["email"] for i in got] == [email]
    inv = admin_client.get(url).json()[0]
    assert {"invitedBy", "createdAt", "expiresAt", "acceptedAt"} <= inv.keys()
    assert admin_client.get(url, params={"status": "bogus"}).status_code == 422


def test_deactivation_kills_sessions_and_links(app, admin_client, db, outbox):
    member = make_user(db, MEMBER)
    m1 = sign_in(_new_client(app), outbox, MEMBER)
    m2 = sign_in(_new_client(app), outbox, MEMBER)
    # An unused link issued before deactivation.
    _new_client(app).post("/auth/request-link", json={"email": MEMBER})
    pending = token_from_mail(outbox.outbox[-1].text)
    assert m1.get("/me").status_code == 200

    r = admin_client.post(f"/api/admin/users/{member.id}/deactivate")
    assert r.status_code == 200 and r.json()["status"] == "deactivated"

    assert m1.get("/me").status_code == 401
    assert m2.get("/me").status_code == 401
    assert (
        db.scalar(
            sa.select(sa.func.count())
            .select_from(Session)
            .where(Session.user_id == member.id)
        )
        == 0
    )
    assert (
        db.scalar(
            sa.select(sa.func.count())
            .select_from(LoginToken)
            .where(LoginToken.user_id == member.id, LoginToken.used_at.is_(None))
        )
        == 0
    )
    c = _new_client(app)
    assert verify(c, pending).status_code == 400
    n = len(outbox.outbox)
    assert c.post("/auth/request-link", json={"email": MEMBER}).status_code == 202
    assert len(outbox.outbox) == n
    assert admin_client.get("/me").status_code == 200


def test_admin_cannot_deactivate_self(admin_client, db):
    admin = db.scalar(sa.select(User).where(User.email == ADMIN))
    r = admin_client.post(f"/api/admin/users/{admin.id}/deactivate")
    assert r.status_code == 400
    assert admin_client.get("/me").status_code == 200


def test_deactivate_unknown_user_404(admin_client):
    assert (
        admin_client.post(f"/api/admin/users/{uuid.uuid4()}/deactivate").status_code
        == 404
    )


def test_second_requested_link_after_acceptance_signs_in_same_member(
    app, admin_client, db, outbox
):
    admin_client.post("/api/admin/invites", json={"email": "new@example.com"})
    c = _new_client(app)
    c.post("/auth/request-link", json={"email": "new@example.com"})
    first = token_from_mail(outbox.outbox[-1].text)
    c.post("/auth/request-link", json={"email": "new@example.com"})
    second = token_from_mail(outbox.outbox[-1].text)
    assert verify(c, first).status_code == 200
    other = _new_client(app)
    assert verify(other, second).status_code == 200
    assert other.get("/me").json()["email"] == "new@example.com"
    assert db.scalar(sa.select(sa.func.count()).select_from(User)) == 2


def test_admin_can_deactivate_another_admin(app, admin_client, db, outbox):
    """Decision 20: allowed; the other admin's sessions end and they cannot sign in."""
    other = make_user(db, "admin2@example.com", role="admin")
    c = sign_in(_new_client(app), outbox, "admin2@example.com")
    r = admin_client.post(f"/api/admin/users/{other.id}/deactivate")
    assert r.status_code == 200 and r.json()["status"] == "deactivated"
    assert c.get("/me").status_code == 401
    assert admin_client.get("/me").status_code == 200


def test_member_routes_live_under_api(app):
    """docs/api-contract.md section 2: Phase 4 member routes are under /api; /auth/*,
    GET /me keep their paths; member source routes are under /api too, and
    admin routes under /api/admin."""
    paths = {(m.upper(), p) for p, ops in app.openapi()["paths"].items() for m in ops}
    for route in [
        ("GET", "/api/feed"),
        ("GET", "/api/shortlist"),
        ("GET", "/api/opportunities/{opportunity_id}"),
        ("PUT", "/api/opportunities/{opportunity_id}/state"),
        ("PUT", "/api/opportunities/{opportunity_id}/note"),
        ("GET", "/api/profiles"),
        ("POST", "/api/profiles"),
        ("GET", "/api/profiles/{profile_id}"),
        ("PATCH", "/api/profiles/{profile_id}"),
        ("DELETE", "/api/profiles/{profile_id}"),
        ("GET", "/api/digest-settings"),
        ("PUT", "/api/digest-settings"),
        ("PATCH", "/api/me"),
        ("DELETE", "/api/me"),
        ("GET", "/api/me/export"),
        ("GET", "/me"),
        ("POST", "/auth/request-link"),
        ("GET", "/api/sources"),
        ("POST", "/api/sources/{source_id}/mute"),
        ("DELETE", "/api/sources/{source_id}/mute"),
        ("GET", "/api/source-suggestions"),
        ("POST", "/api/source-suggestions"),
        ("GET", "/api/admin/sources"),
        ("GET", "/api/admin/source-suggestions"),
    ]:
        assert route in paths, route
    old = {
        "/feed",
        "/shortlist",
        "/profiles",
        "/digest-settings",
        "/me/export",
        "/sources",
        "/source-suggestions",
    }
    assert not old & {p for _, p in paths}
    assert ("PATCH", "/me") not in paths and ("DELETE", "/me") not in paths
    assert not any(p.startswith(("/opportunities", "/admin")) for _, p in paths)


# --- role changes ---------------------------------------------------------------------


def test_admin_promotes_a_member_and_back(app, admin_client, db, outbox):
    member = make_user(db, MEMBER)
    m = sign_in(_new_client(app), outbox, MEMBER)
    assert m.get("/api/admin/users").status_code == 403
    r = admin_client.patch(f"/api/admin/users/{member.id}", json={"role": "admin"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "admin"
    # Role is read on every request: the same session now has admin rights.
    assert m.get("/me").json()["role"] == "admin"
    assert m.get("/api/admin/users").status_code == 200
    r = admin_client.patch(f"/api/admin/users/{member.id}", json={"role": "member"})
    assert r.status_code == 200 and r.json()["role"] == "member"
    assert m.get("/api/admin/users").status_code == 403


def test_admin_cannot_change_own_role(admin_client, db):
    me = db.scalar(sa.select(User).where(User.email == ADMIN))
    for role in ("member", "admin"):
        r = admin_client.patch(f"/api/admin/users/{me.id}", json={"role": role})
        assert r.status_code == 400
    db.refresh(me)
    assert me.role == "admin"


def test_role_change_validates(admin_client, db):
    member = make_user(db, MEMBER)
    url = f"/api/admin/users/{member.id}"
    assert admin_client.patch(url, json={"role": "owner"}).status_code == 422
    assert admin_client.patch(url, json={"status": "active"}).status_code == 422
    assert admin_client.patch(url, json={}).json()["role"] == "member"
    r = admin_client.patch(f"/api/admin/users/{uuid.uuid4()}", json={"role": "admin"})
    assert r.status_code == 404


def test_cannot_demote_or_deactivate_the_last_active_admin(
    app, admin_client, db, outbox
):
    """The caller is always an active admin and cannot act on themselves, so the
    guard bites when the caller has lost admin rights mid-request or when only
    deactivated admins remain besides the target."""
    from blackkite.auth.deps import require_admin
    from blackkite.routes import admin as admin_routes

    other = make_user(db, "admin2@example.com", role="admin")
    old = make_user(db, "old@example.com", role="admin", status="deactivated")
    me = db.scalar(sa.select(User).where(User.email == ADMIN))

    # Simulate a race: by the time the change runs, the caller is no longer an
    # active admin in the database (another admin demoted them).
    stale = User(id=uuid.uuid4(), email="ghost@example.com", role="admin")
    app.dependency_overrides[require_admin] = lambda: stale
    try:
        c = _new_client(app)
        r = c.patch(f"/api/admin/users/{other.id}", json={"role": "member"})
        assert r.status_code == 403
        assert c.post(f"/api/admin/users/{other.id}/deactivate").status_code == 403
    finally:
        del app.dependency_overrides[require_admin]

    # Demoting a deactivated admin is fine: it does not change who is active.
    r = admin_client.patch(f"/api/admin/users/{old.id}", json={"role": "member"})
    assert r.status_code == 200

    # The other admin goes; the caller remains, so it is allowed.
    r = admin_client.patch(f"/api/admin/users/{other.id}", json={"role": "member"})
    assert r.status_code == 200

    # Directly: with the caller as the only active admin, losing them is refused.
    with pytest.raises(admin_routes.HTTPException) as e:
        admin_routes._keep_an_admin(db, me, me)
    assert e.value.status_code == 409
    db.rollback()
    db.refresh(me)
    assert me.role == "admin" and me.status == "active"
