"""Magic-link sign-in, sessions, logout, rate limits (spec 9)."""

from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie

import sqlalchemy as sa
from fastapi.testclient import TestClient

from blackkite.auth.tokens import hash_token
from blackkite.db.models import LoginToken, Session
from tests.conftest import make_user, sign_in, token_from_mail, verify


def _request(client, email):
    return client.post("/auth/request-link", json={"email": email})


def _verify(client, token):
    return verify(client, token)


def test_happy_path(client, db, outbox):
    user = make_user(db, "member@example.com")
    r = _request(client, "Member@Example.com ")
    assert r.status_code == 202
    assert len(outbox.outbox) == 1
    mail = outbox.outbox[0]
    assert mail.to == "member@example.com"
    token = token_from_mail(mail.text)

    # Stored hashed only, with a 15-minute expiry.
    row = db.scalar(sa.select(LoginToken).where(LoginToken.user_id == user.id))
    assert row.token_hash == hash_token(token) and token not in row.token_hash
    life = row.expires_at - row.created_at
    assert timedelta(minutes=14) < life <= timedelta(minutes=15, seconds=5)

    r = _verify(client, token)
    assert r.status_code == 200
    me = client.get("/me")
    assert me.status_code == 200
    assert me.json()["email"] == "member@example.com"
    assert me.json()["role"] == "member"


def test_token_is_single_use(client, db, outbox):
    make_user(db, "member@example.com")
    _request(client, "member@example.com")
    token = token_from_mail(outbox.outbox[0].text)
    assert _verify(client, token).status_code == 200
    other = TestClient(client.app, base_url="https://testserver")
    r = _verify(other, token)
    assert r.status_code == 400
    assert "set-cookie" not in r.headers


def test_expired_token_rejected(client, db, outbox):
    make_user(db, "member@example.com")
    _request(client, "member@example.com")
    token = token_from_mail(outbox.outbox[0].text)
    db.execute(sa.update(LoginToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    r = _verify(client, token)
    assert r.status_code == 400
    assert client.get("/me").status_code == 401


def test_garbage_token_rejected(client):
    assert _verify(client, "not-a-token").status_code == 400


def test_unknown_and_deactivated_get_identical_response(client, db, outbox):
    make_user(db, "member@example.com")
    make_user(db, "gone@example.com", status="deactivated")
    known = _request(client, "member@example.com")
    unknown = _request(client, "nobody@example.com")
    gone = _request(client, "gone@example.com")
    for r in (unknown, gone):
        assert r.status_code == known.status_code == 202
        assert r.json() == known.json()
        assert r.headers.get("content-type") == known.headers.get("content-type")
        assert set(r.headers) == set(known.headers)
    assert [m.to for m in outbox.outbox] == ["member@example.com"]
    assert db.scalar(sa.select(sa.func.count()).select_from(LoginToken)) == 1


def test_session_cookie_flags(client, db, outbox, settings):
    make_user(db, "member@example.com")
    _request(client, "member@example.com")
    r = _verify(client, token_from_mail(outbox.outbox[0].text))
    header = r.headers["set-cookie"]
    morsel = SimpleCookie(header)[settings.session_cookie_name]
    assert morsel["httponly"] is True
    assert morsel["secure"] is True
    assert morsel["samesite"].lower() == "lax"
    assert morsel["path"] == "/"
    assert int(morsel["max-age"]) == 30 * 86400
    # The cookie value is opaque; only its hash is stored, expiring in 30 days.
    raw = morsel.value
    s = db.scalar(sa.select(Session).where(Session.token_hash == hash_token(raw)))
    assert s is not None
    assert timedelta(days=29, hours=23) < s.expires_at - s.created_at <= timedelta(days=30, seconds=5)


def test_secure_flag_can_be_turned_off_for_local_dev(app, settings, db, outbox):
    settings.cookie_secure = False
    make_user(db, "member@example.com")
    with TestClient(app, base_url="http://testserver") as c:
        _request(c, "member@example.com")
        text = outbox.outbox[0].text
        r = _verify(c, token_from_mail(text))
    assert "secure" not in r.headers["set-cookie"].lower()
    assert "httponly" in r.headers["set-cookie"].lower()


def test_expired_session_is_rejected(client, db, outbox):
    make_user(db, "member@example.com")
    sign_in(client, outbox, "member@example.com")
    db.execute(sa.update(Session).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    assert client.get("/me").status_code == 401


def test_logout_deletes_session(client, db, outbox):
    make_user(db, "member@example.com")
    sign_in(client, outbox, "member@example.com")
    assert db.scalar(sa.select(sa.func.count()).select_from(Session)) == 1
    r = client.post("/auth/logout")
    assert r.status_code == 204
    assert db.scalar(sa.select(sa.func.count()).select_from(Session)) == 0
    assert client.get("/me").status_code == 401


def test_logout_without_session_is_harmless(client):
    assert client.post("/auth/logout").status_code == 204


def test_me_requires_sign_in(client):
    assert client.get("/me").status_code == 401


def test_rate_limit_per_email_same_for_known_and_unknown(client, db, settings):
    make_user(db, "member@example.com")
    for email in ("member@example.com", "nobody@example.com"):
        codes = [_request(client, email).status_code
                 for _ in range(settings.link_rate_per_email_per_hour + 1)]
        assert codes[:-1] == [202] * settings.link_rate_per_email_per_hour
        assert codes[-1] == 429


def test_rate_limit_per_ip(client, settings):
    codes = [_request(client, f"n{i}@example.com").status_code
             for i in range(settings.link_rate_per_ip_per_hour + 1)]
    assert codes[-1] == 429
    assert set(codes[:-1]) == {202}


# --- Decision 17: the emailed link opens a confirm page; only POST spends ----------


def test_link_points_at_confirm_page(client, db, outbox):
    make_user(db, "member@example.com")
    _request(client, "member@example.com")
    assert "https://testserver/auth/confirm#token=" in outbox.outbox[0].text
    assert "/auth/verify" not in outbox.outbox[0].text


def test_verify_returns_redirect_json(client, db, outbox, settings):
    make_user(db, "member@example.com")
    _request(client, "member@example.com")
    r = _verify(client, token_from_mail(outbox.outbox[0].text))
    assert r.status_code == 200
    assert r.json() == {"redirect": "/"}
    assert r.headers["cache-control"] == "no-store"
    assert settings.session_cookie_name in r.headers["set-cookie"]


def test_get_verify_spends_nothing(client, db, outbox):
    """A mail scanner fetching the old-style URL must not use the token up."""
    make_user(db, "member@example.com")
    _request(client, "member@example.com")
    token = token_from_mail(outbox.outbox[0].text)
    r = client.get("/auth/verify", params={"token": token}, follow_redirects=False)
    assert r.status_code == 405
    assert "set-cookie" not in r.headers
    assert db.scalar(sa.select(LoginToken.used_at)) is None
    assert _verify(client, token).status_code == 200


def test_head_and_query_string_post_spend_nothing(client, db, outbox):
    make_user(db, "member@example.com")
    _request(client, "member@example.com")
    token = token_from_mail(outbox.outbox[0].text)
    assert client.head("/auth/verify", params={"token": token}).status_code == 405
    # Token in the query string instead of the body: rejected, not spent.
    assert client.post("/auth/verify", params={"token": token}).status_code == 422
    db.expire_all()
    assert db.scalar(sa.select(LoginToken.used_at)) is None


def test_verify_requires_json(client, db, outbox):
    """A cross-site HTML form cannot post a token (login CSRF) without a preflight."""
    make_user(db, "member@example.com")
    _request(client, "member@example.com")
    token = token_from_mail(outbox.outbox[0].text)
    for headers, content in (
        ({"content-type": "text/plain"}, f'{{"token": "{token}"}}'),
        ({"content-type": "application/x-www-form-urlencoded"}, f"token={token}"),
    ):
        r = client.post("/auth/verify", headers=headers, content=content)
        assert r.status_code in (415, 422), r.text
        assert "set-cookie" not in r.headers
    db.expire_all()
    assert db.scalar(sa.select(LoginToken.used_at)) is None
    assert _verify(client, token).status_code == 200


def test_invite_link_points_at_confirm_page(app, db, outbox):
    from tests.conftest import make_user as mk

    mk(db, "admin@example.com", role="admin")
    c = sign_in(TestClient(app, base_url="https://testserver"), outbox, "admin@example.com")
    assert c.post("/admin/invites", json={"email": "new@example.com"}).status_code == 201
    text = outbox.outbox[-1].text
    assert "https://testserver/auth/confirm#token=" in text
    token = token_from_mail(text)
    invitee = TestClient(app, base_url="https://testserver")
    assert invitee.get("/auth/verify", params={"token": token}).status_code == 405
    assert _verify(invitee, token).status_code == 200
    assert invitee.get("/me").json()["email"] == "new@example.com"


# --- Link target: the web origin, token in the fragment ---------------------------


def test_link_default_is_web_origin_with_fragment_token(monkeypatch):
    from urllib.parse import urlparse

    from blackkite.auth.service import confirm_url
    from blackkite.config import Settings

    monkeypatch.delenv("BK_WEB_BASE_URL", raising=False)
    monkeypatch.delenv("BK_PUBLIC_BASE_URL", raising=False)
    url = urlparse(confirm_url(Settings(_env_file=None), "tok-123"))
    assert (url.scheme, url.netloc, url.path) == ("http", "localhost:5173", "/auth/confirm")
    assert url.query == ""  # never in the query: it would reach access logs and Referer
    assert url.fragment == "token=tok-123"


def test_web_base_url_env_and_alias(monkeypatch):
    from blackkite.config import Settings

    monkeypatch.delenv("BK_WEB_BASE_URL", raising=False)
    monkeypatch.setenv("BK_PUBLIC_BASE_URL", "https://old.example.com")
    assert Settings(_env_file=None).web_base_url == "https://old.example.com"
    monkeypatch.setenv("BK_WEB_BASE_URL", "https://app.example.com")
    assert Settings(_env_file=None).web_base_url == "https://app.example.com"
