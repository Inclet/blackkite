"""Settings from env, mail transports."""

from email import message_from_bytes, policy

from blackkite.config import EMBEDDING_DIM, Settings
from blackkite.delivery.mail import (
    ConsoleTransport,
    InlineImage,
    Mail,
    SmtpTransport,
    build_message,
    make_transport,
)


def test_settings_read_bk_prefix_and_key_names(monkeypatch):
    monkeypatch.setenv("BK_COOKIE_SECURE", "false")
    monkeypatch.setenv("BK_MODEL_DIGEST", "claude-opus-5-5")
    monkeypatch.setenv("BK_FIRST_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder")
    s = Settings(_env_file=None)
    assert s.cookie_secure is False
    assert s.model_digest == "claude-opus-5-5"
    assert s.first_admin_email == "owner@example.com"
    assert s.anthropic_api_key.get_secret_value() == "placeholder"
    assert "placeholder" not in repr(s)


def test_defaults_match_spec():
    s = Settings(_env_file=None)
    assert (s.session_days, s.login_token_minutes, s.cookie_secure) == (30, 15, True)
    assert (s.model_extract, s.model_score) == ("claude-haiku-5-5", "claude-haiku-5-5")
    assert EMBEDDING_DIM == 1024


def test_transport_selection():
    assert isinstance(
        make_transport(Settings(_env_file=None, mail_transport="console")),
        ConsoleTransport,
    )
    assert isinstance(
        make_transport(Settings(_env_file=None, mail_transport="smtp")), SmtpTransport
    )


def test_console_transport_prints(capsys):
    ConsoleTransport("Blackkite <no-reply@example.com>").send(
        Mail(to="a@example.com", subject="Hi", text="body")
    )
    out = capsys.readouterr().out
    assert "To: a@example.com" in out and "Subject: Hi" in out and "body" in out


# --- multipart mail (digest and alerts) -------------------------------------------

PNG = b"\x89PNG\r\n\x1a\nfake"


def _html_mail() -> Mail:
    return Mail(
        to="a@example.com",
        subject="Digest",
        text="plain body",
        html='<p>html body</p><img src="cid:kite-logo">',
        inline=(InlineImage(cid="kite-logo", data=PNG, filename="kite.png"),),
    )


def test_build_message_is_alternative_with_related_inline_png():
    msg = message_from_bytes(
        build_message(_html_mail(), "Blackkite <b@example.com>").as_bytes(),
        policy=policy.default,
    )
    assert msg.get_content_type() == "multipart/alternative"
    plain, related = msg.get_payload()
    assert plain.get_content_type() == "text/plain"
    assert plain.get_content().strip() == "plain body"
    assert related.get_content_type() == "multipart/related"
    html, img = related.get_payload()
    assert html.get_content_type() == "text/html"
    assert 'src="cid:kite-logo"' in html.get_content()
    assert img.get_content_type() == "image/png"
    assert img["Content-ID"] == "<kite-logo>"
    assert img.get_content_disposition() == "inline"
    assert img.get_content() == PNG


def test_plain_mail_stays_single_part():
    msg = build_message(Mail(to="a@example.com", subject="s", text="t"), "x@y.z")
    assert msg.get_content_type() == "text/plain"


def test_console_transport_prints_both_parts(capsys):
    ConsoleTransport("Blackkite <b@example.com>").send(_html_mail())
    out = capsys.readouterr().out
    assert "--- text/plain ---\nplain body" in out
    assert "--- text/html ---\n<p>html body</p>" in out
    assert "cid:kite-logo (kite.png, 12 bytes)" in out


def test_smtp_transport_sends_the_multipart_message(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def send_message(self, msg):
            sent.append(("msg", msg))

    import blackkite.delivery.mail as mail_mod

    monkeypatch.setattr(mail_mod.smtplib, "SMTP", FakeSMTP)
    SmtpTransport(Settings(_env_file=None, mail_transport="smtp", smtp_port=1025)).send(
        _html_mail()
    )
    assert sent[0] == ("connect", "localhost", 1025)
    msg = sent[1][1]
    assert msg.get_content_type() == "multipart/alternative"
    assert msg["To"] == "a@example.com"
