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
    """Every (method, path) under /admin or /api/admin, from the OpenAPI schema
    (all are in it)."""
    return {
        (method.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        if path.startswith(("/admin", "/api/admin"))
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
        ("POST", "/admin/invites"),
        ("GET", "/admin/invites"),
        ("DELETE", "/admin/invites/{invite_id}"),
        ("GET", "/admin/users"),
        ("POST", "/admin/users/{user_id}/deactivate"),
        ("GET", "/admin/sources"),
        ("POST", "/admin/sources"),
        ("GET", "/admin/sources/{source_id}"),
        ("PATCH", "/admin/sources/{source_id}"),
        ("POST", "/admin/sources/{source_id}/status"),
        ("GET", "/admin/sources/{source_id}/runs"),
        ("POST", "/admin/sources/test-run"),
        ("POST", "/admin/sources/{source_id}/test-run"),
        ("GET", "/admin/source-suggestions"),
        ("POST", "/admin/source-suggestions/{suggestion_id}/accept"),
        ("POST", "/admin/source-suggestions/{suggestion_id}/reject"),
        ("GET", "/api/admin/catalogue"),
        ("POST", "/api/admin/catalogue/{opportunity_id}/review"),
    }


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
    r = admin_client.post("/admin/invites", json={"email": "New@Example.com"})
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
    assert admin_client.get("/admin/invites").json()[0]["status"] == "accepted"
    # The invite link works once.
    again = verify(_new_client(app), token)
    assert again.status_code == 400
    assert db.scalar(sa.select(sa.func.count()).select_from(User)) == 2


def test_invite_holder_can_request_a_link(app, admin_client, db, outbox):
    admin_client.post("/admin/invites", json={"email": "new@example.com"})
    invitee = sign_in(_new_client(app), outbox, "new@example.com")
    assert invitee.get("/me").json()["role"] == "member"
    assert db.scalar(sa.select(Invite.accepted_at)) is not None


def test_expired_invite_cannot_sign_in(app, admin_client, db, outbox):
    admin_client.post("/admin/invites", json={"email": "new@example.com"})
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
    assert admin_client.get("/admin/invites").json()[0]["status"] == "expired"


def test_deleted_invite_link_stops_working(app, admin_client, db, outbox):
    invite_id = admin_client.post(
        "/admin/invites", json={"email": "new@example.com"}
    ).json()["id"]
    token = token_from_mail(outbox.outbox[-1].text)
    assert admin_client.delete(f"/admin/invites/{invite_id}").status_code == 204
    assert admin_client.delete(f"/admin/invites/{invite_id}").status_code == 404
    r = verify(_new_client(app), token)
    assert r.status_code == 400


def test_cannot_delete_accepted_invite(app, admin_client, outbox):
    invite_id = admin_client.post(
        "/admin/invites", json={"email": "new@example.com"}
    ).json()["id"]
    sign_in(_new_client(app), outbox, "new@example.com")
    assert admin_client.delete(f"/admin/invites/{invite_id}").status_code == 409


def test_cannot_invite_existing_user(admin_client, db):
    make_user(db, MEMBER)
    assert (
        admin_client.post("/admin/invites", json={"email": MEMBER.upper()}).status_code
        == 409
    )


def test_reinvite_replaces_pending_invite(admin_client, db, outbox):
    admin_client.post("/admin/invites", json={"email": "new@example.com"})
    old = token_from_mail(outbox.outbox[-1].text)
    admin_client.post("/admin/invites", json={"email": "new@example.com"})
    assert db.scalar(sa.select(sa.func.count()).select_from(Invite)) == 1
    c = TestClient(admin_client.app, base_url="https://testserver")
    assert verify(c, old).status_code == 400


def test_list_users(admin_client, db):
    make_user(db, MEMBER)
    emails = [u["email"] for u in admin_client.get("/admin/users").json()]
    assert emails == [ADMIN, MEMBER]


def test_deactivation_kills_sessions_and_links(app, admin_client, db, outbox):
    member = make_user(db, MEMBER)
    m1 = sign_in(_new_client(app), outbox, MEMBER)
    m2 = sign_in(_new_client(app), outbox, MEMBER)
    # An unused link issued before deactivation.
    _new_client(app).post("/auth/request-link", json={"email": MEMBER})
    pending = token_from_mail(outbox.outbox[-1].text)
    assert m1.get("/me").status_code == 200

    r = admin_client.post(f"/admin/users/{member.id}/deactivate")
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
    r = admin_client.post(f"/admin/users/{admin.id}/deactivate")
    assert r.status_code == 400
    assert admin_client.get("/me").status_code == 200


def test_deactivate_unknown_user_404(admin_client):
    assert (
        admin_client.post(f"/admin/users/{uuid.uuid4()}/deactivate").status_code == 404
    )


def test_second_requested_link_after_acceptance_signs_in_same_member(
    app, admin_client, db, outbox
):
    admin_client.post("/admin/invites", json={"email": "new@example.com"})
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
    r = admin_client.post(f"/admin/users/{other.id}/deactivate")
    assert r.status_code == 200 and r.json()["status"] == "deactivated"
    assert c.get("/me").status_code == 401
    assert admin_client.get("/me").status_code == 200


def test_member_routes_live_under_api(app):
    """docs/api-contract.md section 2: Phase 4 member routes are under /api; /auth/*,
    GET /me and the earlier /admin/* keep their paths; member source routes are
    under /api too."""
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
        ("GET", "/admin/sources"),
        ("GET", "/admin/source-suggestions"),
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
    assert not any(
        p.startswith(("/opportunities", "/admin/catalogue")) for _, p in paths
    )
