"""One-click unsubscribe (decision 43, RFC 8058): signed links in every digest and
alert, List-Unsubscribe headers, and POST /api/unsubscribe without a session."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from email import message_from_bytes
from email.policy import default as default_policy
from urllib.parse import parse_qs, urlsplit

import pytest
import sqlalchemy as sa
from alembic import command
from fastapi.testclient import TestClient

from blackkite.db.models import DigestLog, DigestSetting
from blackkite.delivery import unsubscribe as U
from blackkite.delivery.alerts import send_alerts
from blackkite.delivery.build import send_digest
from blackkite.delivery.mail import MemoryTransport, build_message, format_console
from tests import factories as f
from tests.conftest import alembic_config, make_user
from tests.factories import KIGALI, NOW, kigali

MONDAY = datetime(2026, 11, 30, 7, 0, tzinfo=KIGALI)


@pytest.fixture
def ana(db):
    u = make_user(db, "ana@example.com")
    db.add(
        DigestSetting(
            user_id=u.id,
            channel="email",
            address="ana.digest@example.com",
            alert_min_fit="good",
        )
    )
    db.commit()
    return u


@pytest.fixture
def anon(app):
    """A client with no session."""
    with TestClient(app, base_url="https://testserver") as c:
        yield c


def _setting(db, user) -> DigestSetting | None:
    db.expire_all()
    return db.scalar(sa.select(DigestSetting).where(DigestSetting.user_id == user.id))


def _token_from(url: str) -> str:
    parts = urlsplit(url)
    assert parts.path == "/unsubscribe"
    return parse_qs(parts.fragment)["token"][0]


def _digest_mail(db, user, settings):
    src = f.source(db, "Src")
    prof = f.profile(db, user, "Ironji-Trade")
    o = f.opportunity(db, "Cold chain", deadline_at=kigali(2026, 12, 10))
    f.link(db, o, src)
    f.score(db, user, o, prof, 80, fit_word="strong")
    db.commit()
    out = MemoryTransport()
    assert send_digest(db, user, settings, out, MONDAY).status == "sent"
    return out.outbox[0]


# --- tokens -------------------------------------------------------------------------


def test_tokens_are_signed_per_kind_and_user(db, ana, settings):
    ben = make_user(db, "ben@example.com")
    t = U.make_token(settings, ana, "digest")
    claims = U.read_token(settings, t)
    assert claims == U.TokenClaims(ana.id, "digest", ana.unsubscribe_nonce)
    assert U.read_token(settings, U.make_token(settings, ana, "alert")).kind == "alert"
    assert t != U.make_token(settings, ana, "alert")
    assert t != U.make_token(settings, ben, "digest")
    assert set(t) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    )
    # Any change to the token breaks it.
    raw = bytearray(base64.urlsafe_b64decode(t + "=" * (-len(t) % 4)))
    for i in (1, 5, 30, len(raw) - 1):
        bad = bytearray(raw)
        bad[i] ^= 1
        forged = base64.urlsafe_b64encode(bytes(bad)).rstrip(b"=").decode()
        assert U.read_token(settings, forged) is None
    other = settings.model_copy(
        update={
            "unsubscribe_secret": type(settings.unsubscribe_secret)(
                "other-secret-0123456789abcdefghij"
            )
        }
    )
    assert U.read_token(other, t) is None
    for junk in ("", "abc", "!" * 67, t + "A", t[:-1]):
        assert U.read_token(settings, junk) is None


def test_no_secret_no_token(db, ana, settings):
    bare = settings.model_copy(update={"unsubscribe_secret": None})
    with pytest.raises(U.UnsubscribeNotConfigured):
        U.make_token(bare, ana, "digest")


def test_secret_must_be_long_and_empty_means_unset():
    from pydantic import ValidationError

    from blackkite.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, unsubscribe_secret="short")
    assert Settings(_env_file=None, unsubscribe_secret="").unsubscribe_secret is None
    assert Settings(_env_file=None, api_public_url=" ").api_public_url is None


def test_rotating_the_nonce_revokes_old_links(db, ana, settings, anon):
    old = U.make_token(settings, ana, "digest")
    U.rotate_nonce(ana)
    db.commit()
    r = anon.post("/api/unsubscribe", json={"token": old})
    assert r.status_code == 400
    assert _setting(db, ana).frequency == "weekly"
    new = U.make_token(settings, ana, "digest")
    assert anon.post("/api/unsubscribe", json={"token": new}).status_code == 200


def test_users_get_distinct_nonces(db):
    a = make_user(db, "a@example.com")
    b = make_user(db, "b@example.com")
    assert len(a.unsubscribe_nonce) == 32 and a.unsubscribe_nonce != b.unsubscribe_nonce
    int(a.unsubscribe_nonce, 16)


def test_migration_gives_existing_users_distinct_nonces(make_database):
    url = make_database("bk_migr")
    cfg = alembic_config(url)
    command.upgrade(cfg, "0010")
    eng = sa.create_engine(url)
    try:
        with eng.begin() as c:
            c.execute(
                sa.text(
                    "INSERT INTO \"user\" (email) VALUES ('a@example.com'), "
                    "('b@example.com')"
                )
            )
        command.upgrade(cfg, "0011")
        with eng.connect() as c:
            nonces = c.scalars(sa.text('SELECT unsubscribe_nonce FROM "user"')).all()
        assert len(set(nonces)) == 2 and all(len(n) == 32 for n in nonces)
        for n in nonces:
            int(n, 16)
        command.downgrade(cfg, "0010")
    finally:
        eng.dispose()


# --- emails --------------------------------------------------------------------------


def test_digest_carries_the_link_and_rfc8058_headers(db, ana, settings):
    mail = _digest_mail(db, ana, settings)
    headers = dict(mail.headers)
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    one_click = headers["List-Unsubscribe"]
    # No mailto unless one is configured; the API origin defaults to the web's.
    assert one_click.startswith("<https://testserver/api/unsubscribe?token=")
    assert "mailto:" not in one_click and one_click.count("<") == 1
    header_token = parse_qs(urlsplit(one_click[1:-1]).query)["token"][0]
    [link] = [
        w for w in mail.text.split() if w.startswith("https://testserver/unsubscribe")
    ]
    assert _token_from(link) == header_token
    assert U.read_token(settings, header_token).kind == "digest"
    assert f'href="{link}"' in mail.html
    # "Change how often" still goes to the settings page.
    assert "Change how often: https://testserver/settings/digest" in mail.text
    # The headers survive MIME on one line each (no encoded words).
    raw = bytes(build_message(mail, settings.mail_from))
    assert f"List-Unsubscribe: {one_click}".encode() in raw
    parsed = message_from_bytes(raw, policy=default_policy)
    assert parsed["List-Unsubscribe"] == one_click
    assert "List-Unsubscribe: <https://testserver" in format_console(mail, "x")


def test_api_origin_and_mailto_from_settings(db, ana, settings):
    s = settings.model_copy(
        update={
            "api_public_url": "https://api.example.com/",
            "unsubscribe_mailto": "unsubscribe@example.com",
        }
    )
    links = U.links(s, ana, "digest")
    one_click, mailto = dict(links.headers)["List-Unsubscribe"].split(", ")
    assert one_click.startswith("<https://api.example.com/api/unsubscribe?token=")
    assert mailto.startswith("<mailto:unsubscribe@example.com?subject=unsubscribe%20")
    assert links.page_url.startswith("https://testserver/unsubscribe#token=")


def test_alert_carries_an_alert_link_and_headers(db, ana, settings):
    src = f.source(db, "Src")
    prof = f.profile(db, ana, "Ironji-Trade")
    o = f.opportunity(
        db,
        "Urgent",
        deadline_at=NOW + timedelta(days=2),
        created_at=kigali(2026, 11, 24, 9),
    )
    f.link(db, o, src)
    f.score(db, ana, o, prof, 90, fit_word="strong").created_at = o.created_at
    db.commit()
    out = MemoryTransport()
    assert send_alerts(db, ana, settings, out, NOW) == 1
    [mail] = out.outbox
    headers = dict(mail.headers)
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    [link] = [
        w for w in mail.text.split() if w.startswith("https://testserver/unsubscribe")
    ]
    assert U.read_token(settings, _token_from(link)).kind == "alert"
    assert "Stop these alerts: " + link in mail.text
    assert f'href="{link}"' in mail.html and "stop these alerts" in mail.html


def test_no_secret_sends_nothing_and_logs_nothing(db, ana, settings):
    bare = settings.model_copy(update={"unsubscribe_secret": None})
    src = f.source(db, "Src")
    prof = f.profile(db, ana, "P")
    o = f.opportunity(db, "Cold chain", deadline_at=kigali(2026, 12, 10))
    f.link(db, o, src)
    f.score(db, ana, o, prof, 80, fit_word="strong")
    db.commit()
    out = MemoryTransport()
    with pytest.raises(U.UnsubscribeNotConfigured):
        send_digest(db, ana, bare, out, MONDAY)
    db.rollback()
    assert out.outbox == []
    assert db.scalar(sa.select(sa.func.count()).select_from(DigestLog)) == 0


# --- POST /api/unsubscribe --------------------------------------------------------------


def test_web_page_post_turns_the_digest_off_idempotently(db, ana, settings, anon):
    token = U.make_token(settings, ana, "digest")
    for _ in range(2):
        r = anon.post("/api/unsubscribe", json={"token": token})
        assert r.status_code == 200, r.text
        assert r.json() == {
            "kind": "digest",
            "detail": "You won't get these emails any more.",
        }
        assert r.headers["cache-control"] == "no-store"
        s = _setting(db, ana)
        assert s.frequency == "off" and s.alert_min_fit == "good"


def test_alert_token_turns_alerts_off_only(db, ana, settings, anon):
    r = anon.post(
        "/api/unsubscribe", json={"token": U.make_token(settings, ana, "alert")}
    )
    assert r.status_code == 200 and r.json()["kind"] == "alert"
    s = _setting(db, ana)
    assert s.alert_min_fit is None and s.frequency == "weekly"


def test_digest_off_without_a_settings_row(db, settings, anon):
    ben = make_user(db, "ben@example.com")
    r = anon.post(
        "/api/unsubscribe", json={"token": U.make_token(settings, ben, "digest")}
    )
    assert r.status_code == 200
    s = _setting(db, ben)
    assert (s.channel, s.address, s.frequency) == ("email", ben.email, "off")
    # An alert token with no row: alerts are already off; nothing is created.
    carl = make_user(db, "carl@example.com")
    r = anon.post(
        "/api/unsubscribe", json={"token": U.make_token(settings, carl, "alert")}
    )
    assert r.status_code == 200 and _setting(db, carl) is None


def test_only_the_tokens_user_is_changed(db, ana, settings, anon):
    ben = make_user(db, "ben@example.com")
    db.add(DigestSetting(user_id=ben.id, channel="email", address=ben.email))
    db.commit()
    anon.post("/api/unsubscribe", json={"token": U.make_token(settings, ana, "digest")})
    assert _setting(db, ben).frequency == "weekly"


@pytest.mark.parametrize("kind", ["urlencoded", "multipart"])
def test_rfc8058_one_click_post(db, ana, settings, anon, kind):
    token = U.make_token(settings, ana, "digest")
    url = f"/api/unsubscribe?token={token}"
    if kind == "urlencoded":
        r = anon.post(url, data={"List-Unsubscribe": "One-Click"})
    else:
        r = anon.post(url, files={"List-Unsubscribe": (None, "One-Click")})
    assert r.status_code == 200, r.text
    assert _setting(db, ana).frequency == "off"


def test_one_click_post_needs_the_one_click_body(db, ana, settings, anon):
    token = U.make_token(settings, ana, "digest")
    url = f"/api/unsubscribe?token={token}"
    assert anon.post(url, data={"List-Unsubscribe": "Other"}).status_code == 400
    form = {"content-type": "application/x-www-form-urlencoded"}
    assert anon.post(url, content=b"", headers=form).status_code == 400
    assert (
        anon.post(url, content=b"x", headers={"content-type": "text/plain"})
    ).status_code == 415
    assert (
        anon.post("/api/unsubscribe", data={"List-Unsubscribe": "One-Click"})
    ).status_code == 422
    assert anon.post("/api/unsubscribe", json={}).status_code == 422
    assert _setting(db, ana).frequency == "weekly"


def test_bad_or_deleted_users_token_is_refused(db, ana, settings, anon):
    r = anon.post("/api/unsubscribe", json={"token": "A" * 67})
    assert r.status_code == 400
    assert r.json()["detail"].startswith("This unsubscribe link is not valid")
    ben = make_user(db, "ben@example.com")
    token = U.make_token(settings, ben, "digest")
    db.delete(ben)
    db.commit()
    assert anon.post("/api/unsubscribe", json={"token": token}).status_code == 400
    assert _setting(db, ana).frequency == "weekly"


def test_get_changes_nothing(db, ana, settings, anon):
    token = U.make_token(settings, ana, "digest")
    r = anon.get(f"/api/unsubscribe?token={token}")
    assert r.status_code == 405 and r.headers["allow"] == "POST"
    assert "Use POST" in r.json()["detail"]
    assert _setting(db, ana).frequency == "weekly"


def test_rate_limited_per_token_not_per_shared_address(db, settings, anon):
    """Many users' one-click POSTs from one provider address all go through; one
    token repeated past its limit is refused, and others are not affected."""
    assert settings.unsubscribe_rate_per_token_per_hour == 10
    users = [make_user(db, f"u{i}@example.com") for i in range(25)]
    for u in users:  # 25 > the old per-IP limit of 20, all from one address
        url = f"/api/unsubscribe?token={U.make_token(settings, u, 'digest')}"
        r = anon.post(url, data={"List-Unsubscribe": "One-Click"})
        assert r.status_code == 200, r.text
    token = U.make_token(settings, users[0], "alert")
    for _ in range(10):
        assert anon.post("/api/unsubscribe", json={"token": token}).status_code == 200
    r = anon.post("/api/unsubscribe", json={"token": token})
    assert r.status_code == 429
    other = U.make_token(settings, users[1], "alert")
    assert anon.post("/api/unsubscribe", json={"token": other}).status_code == 200


def test_per_address_flood_ceiling(db, ana, settings, app):
    from blackkite.auth.ratelimit import UnsubscribeLimiter

    app.state.unsubscribe_limiter = UnsubscribeLimiter(per_token=100, per_ip=3)
    with TestClient(app, base_url="https://testserver") as c:
        for _ in range(3):
            assert (
                c.post("/api/unsubscribe", json={"token": "A" * 67}).status_code == 400
            )
        r = c.post(
            "/api/unsubscribe", json={"token": U.make_token(settings, ana, "digest")}
        )
        assert r.status_code == 429
    assert _setting(db, ana).frequency == "weekly"


def test_limiter_keeps_token_hashes_not_tokens():
    from blackkite.auth.ratelimit import UnsubscribeLimiter

    lim = UnsubscribeLimiter(per_token=1, per_ip=10)
    assert lim.allow_token("secret-token") and not lim.allow_token("secret-token")
    assert "secret-token" not in lim.token._hits
    assert lim.allow_token("another")
