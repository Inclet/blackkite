"""Resend mail transport (decision 45). Never reaches the real API: every test
uses an httpx.MockTransport, and the safety switch is off by default."""

from __future__ import annotations

import base64
import json
import logging

import httpx
import pytest

from blackkite.config import Settings
from blackkite.delivery.mail import InlineImage, Mail, make_transport
from blackkite.delivery.resend import (
    RESEND_EMAILS_URL,
    RealSendDisabled,
    ResendError,
    ResendNotConfigured,
    ResendTransport,
)

FAKE_KEY = "re_test_placeholder_not_a_key"
SENDER = "Blackkite <digest@example.com>"
PNG = b"\x89PNG\r\n\x1a\nfake"


def _settings(**kw) -> Settings:
    base = {
        "mail_transport": "resend",
        "mail_from": SENDER,
        "resend_api_key": FAKE_KEY,
    }
    return Settings(_env_file=None, **{**base, **kw})


def _mail() -> Mail:
    return Mail(
        to="ana@example.com",
        subject="Two things this week",
        text="plain body",
        html='<p>html body</p><img src="cid:kite-logo">',
        inline=(InlineImage(cid="kite-logo", data=PNG, filename="kite.png"),),
        headers=(
            ("List-Unsubscribe", "<https://app.example/api/unsubscribe?token=T>"),
            ("List-Unsubscribe-Post", "List-Unsubscribe=One-Click"),
        ),
    )


class Recorder:
    def __init__(self, status: int = 200, body: dict | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.status = status
        self.body = body if body is not None else {"id": "email-123"}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json=self.body)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def test_selected_by_setting_and_needs_key_and_sender(monkeypatch):
    for name in ("RESEND_API_KEY", "BK_MAIL_FROM", "BK_MAIL_ALLOW_REAL_SEND"):
        monkeypatch.delenv(name, raising=False)
    assert isinstance(make_transport(_settings()), ResendTransport)
    with pytest.raises(ResendNotConfigured, match="RESEND_API_KEY"):
        make_transport(
            Settings(_env_file=None, mail_transport="resend", mail_from=SENDER)
        )
    with pytest.raises(ResendNotConfigured, match="BK_MAIL_FROM"):
        make_transport(
            Settings(_env_file=None, mail_transport="resend", resend_api_key=FAKE_KEY)
        )
    # From the environment, as deployed.
    monkeypatch.setenv("BK_MAIL_TRANSPORT", "resend")
    monkeypatch.setenv("RESEND_API_KEY", FAKE_KEY)
    monkeypatch.setenv("BK_MAIL_FROM", SENDER)
    s = Settings(_env_file=None)
    assert isinstance(make_transport(s), ResendTransport)
    assert s.mail_allow_real_send is False
    assert FAKE_KEY not in repr(s)


def test_safety_switch_off_refuses_and_logs(caplog):
    rec = Recorder()
    t = ResendTransport(_settings(), client=rec.client())
    with (
        caplog.at_level(logging.WARNING, "blackkite.mail"),
        pytest.raises(RealSendDisabled),
    ):
        t.send(_mail())
    assert rec.requests == []
    logged = caplog.text
    assert "would have sent" in logged
    assert "ana@example.com" in logged and "Two things this week" in logged
    assert "List-Unsubscribe" in logged
    # Never the body, the header values or the key.
    for secret in ("plain body", "html body", "token=T", FAKE_KEY):
        assert secret not in logged


def test_sends_the_documented_payload_when_allowed(caplog):
    rec = Recorder()
    t = ResendTransport(_settings(mail_allow_real_send=True), client=rec.client())
    with caplog.at_level(logging.INFO, "blackkite.mail"):
        t.send(_mail())
    [req] = rec.requests
    assert str(req.url) == RESEND_EMAILS_URL == "https://api.resend.com/emails"
    assert req.method == "POST"
    assert req.headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert req.headers["content-type"] == "application/json"
    body = json.loads(req.content)
    assert body == {
        "from": SENDER,
        "to": ["ana@example.com"],
        "subject": "Two things this week",
        "text": "plain body",
        "html": '<p>html body</p><img src="cid:kite-logo">',
        "attachments": [
            {
                "filename": "kite.png",
                "content": base64.b64encode(PNG).decode(),
                "content_type": "image/png",
                "content_id": "kite-logo",
            }
        ],
        "headers": {
            "List-Unsubscribe": "<https://app.example/api/unsubscribe?token=T>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    }
    assert "email-123" in caplog.text and FAKE_KEY not in caplog.text


def test_plain_mail_has_no_html_attachments_or_headers():
    rec = Recorder()
    t = ResendTransport(_settings(mail_allow_real_send=True), client=rec.client())
    t.send(Mail(to="a@example.com", subject="Sign in", text="link"))
    body = json.loads(rec.requests[0].content)
    assert set(body) == {"from", "to", "subject", "text"}


@pytest.mark.parametrize("status", [400, 401, 422, 429, 500])
def test_error_answers_raise_without_retry(status):
    rec = Recorder(status=status, body={"message": "nope"})
    t = ResendTransport(_settings(mail_allow_real_send=True), client=rec.client())
    with pytest.raises(ResendError, match=str(status)) as info:
        t.send(_mail())
    assert len(rec.requests) == 1
    assert FAKE_KEY not in str(info.value)


def test_network_error_raises_resend_error():
    def boom(request):
        raise httpx.ConnectError("down", request=request)

    client = httpx.Client(transport=httpx.MockTransport(boom))
    t = ResendTransport(_settings(mail_allow_real_send=True), client=client)
    with pytest.raises(ResendError, match="ConnectError"):
        t.send(_mail())


def test_refused_digest_is_not_logged_as_sent(db, settings):
    """A refusal (switch off) leaves no digest_log row, so it is not recorded as
    sent."""
    import sqlalchemy as sa

    from blackkite.db.models import DigestLog, DigestSetting
    from blackkite.delivery.build import send_digest
    from tests import factories as f
    from tests.conftest import make_user
    from tests.factories import kigali
    from tests.test_unsubscribe import MONDAY

    ana = make_user(db, "ana@example.com")
    db.add(DigestSetting(user_id=ana.id, channel="email", address=ana.email))
    src = f.source(db, "Src")
    prof = f.profile(db, ana, "P")
    o = f.opportunity(db, "Cold chain", deadline_at=kigali(2026, 12, 10))
    f.link(db, o, src)
    f.score(db, ana, o, prof, 80, fit_word="strong")
    db.commit()
    rec = Recorder()
    resend = ResendTransport(
        settings.model_copy(
            update={"mail_from": SENDER, "resend_api_key": _settings().resend_api_key}
        ),
        client=rec.client(),
    )
    with pytest.raises(RealSendDisabled):
        send_digest(db, ana, settings, resend, MONDAY)
    assert rec.requests == []
    assert db.scalar(sa.select(sa.func.count()).select_from(DigestLog)) == 0
