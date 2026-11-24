"""Settings from env, mail transports."""

from blackkite.config import EMBEDDING_DIM, Settings
from blackkite.delivery.mail import ConsoleTransport, Mail, SmtpTransport, make_transport


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
    assert isinstance(make_transport(Settings(_env_file=None, mail_transport="console")),
                      ConsoleTransport)
    assert isinstance(make_transport(Settings(_env_file=None, mail_transport="smtp")),
                      SmtpTransport)


def test_console_transport_prints(capsys):
    ConsoleTransport("Blackkite <no-reply@example.com>").send(
        Mail(to="a@example.com", subject="Hi", text="body"))
    out = capsys.readouterr().out
    assert "To: a@example.com" in out and "Subject: Hi" in out and "body" in out
