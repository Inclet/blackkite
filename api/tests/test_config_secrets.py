"""Secrets: example values from .env.example and weak strings are refused at
startup (Settings) and again when an unsubscribe link is signed."""

import secrets
import uuid
from pathlib import Path

import pytest
from dotenv import dotenv_values
from pydantic import SecretStr, ValidationError

from blackkite.config import Settings, placeholder_problem, secret_problem
from blackkite.db.models import User
from blackkite.delivery import unsubscribe as U

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
OLD_EXAMPLE = "replace-with-a-random-secret-of-at-least-32-chars"
URL = "postgresql+psycopg://blackkite:{}@localhost:5432/blackkite"


@pytest.mark.parametrize(
    "value",
    [
        OLD_EXAMPLE,
        OLD_EXAMPLE.upper(),
        "change-me-change-me-change-me-change-me",
        "your-unsubscribe-secret-goes-here-0123456789",
        "an-example-secret-value-with-0123456789-digits",
        "PLACEHOLDER_abcdefghijklmnopqrstuvwxyz0123",
        "x" * 40,
        "ab" * 20,
        "0123456789a" * 4,  # 11 different characters
    ],
)
def test_weak_or_example_unsubscribe_secret_refused_at_startup(value):
    with pytest.raises(ValidationError) as e:
        Settings(_env_file=None, unsubscribe_secret=value)
    text = str(e.value)
    assert "BK_UNSUBSCRIBE_SECRET" in text
    assert value not in text  # the value is never echoed


def test_short_secret_refused_and_generated_ones_accepted():
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(_env_file=None, unsubscribe_secret="Zq8#kP2!mV7@xR4$wL9%")
    for _ in range(200):
        for value in (secrets.token_hex(32), secrets.token_urlsafe(32)):
            s = Settings(_env_file=None, unsubscribe_secret=value)
            assert s.unsubscribe_secret.get_secret_value() == value
    assert Settings(_env_file=None, unsubscribe_secret="  ").unsubscribe_secret is None


def test_refused_from_the_environment(monkeypatch):
    monkeypatch.setenv("BK_UNSUBSCRIBE_SECRET", OLD_EXAMPLE)
    with pytest.raises(ValidationError, match="BK_UNSUBSCRIBE_SECRET"):
        Settings(_env_file=None)


@pytest.mark.parametrize("password", ["change-me", "CHANGEME", "password"])
def test_example_database_password_refused(password):
    with pytest.raises(ValidationError, match="BK_DATABASE_URL") as e:
        Settings(_env_file=None, database_url=URL.format(password))
    assert URL.format(password) not in str(e.value)


def test_real_or_absent_database_password_accepted():
    for url in (
        URL.format(secrets.token_hex(12)),
        URL.format("blackkite"),
        URL.format(""),
    ):
        assert Settings(_env_file=None, database_url=url).database_url == url
    local = "postgresql+psycopg://tester@127.0.0.1:5999/postgres"
    assert Settings(_env_file=None, database_url=local).database_url == local


def test_env_example_secrets_are_empty_or_refused():
    """Every secret in .env.example is empty, or is refused as it stands."""
    values = dotenv_values(ENV_EXAMPLE)
    for name in (
        "POSTGRES_PASSWORD",
        "BK_UNSUBSCRIBE_SECRET",
        "BK_SMTP_PASSWORD",
        "BK_INGEST_IMAP_PASSWORD",
        "BK_RENDERER_TOKEN",
        "ANTHROPIC_API_KEY",
        "VOYAGE_API_KEY",
        "BRAVE_API_KEY",
        "RESEND_API_KEY",
    ):
        assert values[name] == "", name
    for name, value in values.items():
        if name.endswith(("_PASSWORD", "_SECRET", "_KEY", "_TOKEN")):
            assert not value, name
    # Example URLs carry no password that would be accepted.
    url = values.get("BK_DATABASE_URL")
    assert url is None or placeholder_problem(url) is not None
    # The example, loaded as a .env, is accepted (nothing set is a placeholder).
    Settings(_env_file=ENV_EXAMPLE)


def test_signing_refuses_a_weak_secret_even_without_validation():
    user = User(email="a@example.com", unsubscribe_nonce=secrets.token_hex(16))
    user.id = uuid.uuid4()
    good = Settings(_env_file=None, unsubscribe_secret=secrets.token_hex(32))
    assert U.make_token(good, user, "digest")
    for weak in (OLD_EXAMPLE, "x" * 40):
        bad = good.model_copy(update={"unsubscribe_secret": SecretStr(weak)})
        with pytest.raises(U.UnsubscribeNotConfigured, match="BK_UNSUBSCRIBE_SECRET"):
            U.make_token(bad, user, "digest")
    assert secret_problem(OLD_EXAMPLE) == "is an example value"
