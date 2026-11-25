"""Settings, read from environment variables (prefix BK_) or a .env file.

Third-party API keys keep their conventional names without the prefix
(ANTHROPIC_API_KEY, VOYAGE_API_KEY, BRAVE_API_KEY, RESEND_API_KEY).
"""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Secrets (spec 10): values copied from .env.example or docs, and strings with
# too little variety, are refused rather than trusted as keys or passwords.
# Known example values, compared case-insensitively after trimming.
KNOWN_PLACEHOLDERS = frozenset(
    {
        "change-me",
        "changeme",
        "change_me",
        "password",
        "secret",
        "replace-me",
        "replace_me",
        "placeholder",
        "replace-with-a-random-secret-of-at-least-32-chars",
    }
)
# Words that mark a value as an example rather than a generated secret.
PLACEHOLDER_MARKERS = (
    "replace-with",
    "replace_with",
    "change-me",
    "changeme",
    "placeholder",
    "example",
    "your-",
    "your_",
    "xxxxxxxx",
)
# Fewest distinct characters a signing secret may have. 12, not 16: a
# `openssl rand -hex 32` value (64 hex digits) lacks at least one of the 16
# digits about one time in four, but almost never has fewer than 12.
MIN_SECRET_DISTINCT_CHARS = 12


def placeholder_problem(value: str) -> str | None:
    """Why ``value`` looks like an example value, or None."""
    v = value.strip().lower()
    if v in KNOWN_PLACEHOLDERS:
        return "is an example value"
    if any(m in v for m in PLACEHOLDER_MARKERS):
        return "looks like an example value"
    return None


def secret_problem(value: str, *, min_length: int = 32) -> str | None:
    """Why ``value`` cannot be used as a signing secret, or None."""
    if problem := placeholder_problem(value):
        return problem
    if len(value) < min_length:
        return f"must be at least {min_length} characters"
    if len(set(value)) < MIN_SECRET_DISTINCT_CHARS:
        return (
            f"has fewer than {MIN_SECRET_DISTINCT_CHARS} different characters; "
            "use a random value"
        )
    return None


GENERATE_HINT = "generate one with `openssl rand -hex 32`"


# Dimension of opportunity.embedding. Voyage AI embedding models (decision 12)
# return 1024-dimensional vectors by default. Changing this needs a migration
# that alters the column type, and every stored embedding must be recomputed.
EMBEDDING_DIM = 1024


class Settings(BaseSettings):
    # Errors never echo the value: it may be a secret.
    model_config = SettingsConfigDict(
        env_prefix="BK_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    # Where this runs: "dev" on a developer's machine, "prod" on the VPS (set
    # BK_ENV=prod in the deploy .env). Dev-only commands (bk demo-seed) refuse
    # to run unless it is "dev".
    env: Literal["dev", "prod"] = "dev"

    # Database (SQLAlchemy URL, psycopg 3 driver)
    database_url: str = (
        "postgresql+psycopg://blackkite:blackkite@localhost:5432/blackkite"
    )

    # Origin of the WEB app; emailed sign-in and invite links point at its
    # /auth/confirm page (a web route, not an API path). Set only by
    # BK_WEB_BASE_URL; the old BK_PUBLIC_BASE_URL is ignored (see
    # warn_ignored_env) because it used to hold the API origin.
    web_base_url: str = "http://localhost:5173"
    # Where the confirm page sends the browser after POST /auth/verify succeeds
    after_login_url: str = "/"

    # Sessions and tokens
    session_cookie_name: str = "bk_session"
    cookie_secure: bool = True  # set false only for local http development
    session_days: int = 30
    login_token_minutes: int = 15
    invite_days: int = 7

    # Rate limits on POST /auth/request-link (sliding one-hour window, per process)
    link_rate_per_email_per_hour: int = 5
    link_rate_per_ip_per_hour: int = 20
    # Rate limits on POST /api/unsubscribe (decision 43): per token, so one-click
    # POSTs from a mail provider's shared addresses are not blocked, plus a
    # generous per-address ceiling against floods.
    unsubscribe_rate_per_token_per_hour: int = Field(default=10, ge=1)
    unsubscribe_rate_per_ip_per_hour: int = Field(default=300, ge=1)

    # Member source suggestions (spec 4.3): at most this many per user in any
    # 24 hours; more get 429.
    suggestions_per_user_per_day: int = Field(default=10, ge=1)
    # Admin test runs (spec 4.3 step 2), all collector types including
    # browser_list: at most this many at once in the API process; more get 429.
    test_runs_max_concurrent: int = Field(default=2, ge=1)

    # Mail
    mail_transport: Literal["console", "smtp", "resend"] = "console"
    # Sender. The resend transport requires it to be set explicitly.
    mail_from: str = "Blackkite <no-reply@example.com>"
    # Safety switch for providers that deliver real email (resend, decision 45).
    # While false the resend transport refuses to send and logs what it would
    # have sent. Set true only with the owner's go-ahead.
    mail_allow_real_send: bool = False
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False

    # One-click unsubscribe (decision 43). Links in every digest and alert are
    # HMAC-signed with this secret (at least 32 characters; required to send
    # digests and alerts). Changing it revokes every link already sent.
    unsubscribe_secret: SecretStr | None = None
    # Public origin of the API, for the List-Unsubscribe one-click URL
    # ({api_public_url}/api/unsubscribe?token=...). Unset: the web origin, which
    # proxies /api/* to the API.
    api_public_url: str | None = None
    # Optional address for a List-Unsubscribe mailto: link. Unset: no mailto.
    unsubscribe_mailto: str | None = None

    # Weekly digest: Mondays at this hour, Africa/Kigali (decision 18).
    digest_hour: int = Field(default=7, ge=0, le=23)

    # Bootstrap
    first_admin_email: str | None = None

    # Collectors (spec 10: identify honestly, rate-limit, cache, never retry hard)
    # Page that says who runs the bot and how to reach them; goes in the User-Agent.
    bot_contact_url: str | None = None
    fetch_timeout_seconds: float = 20.0
    fetch_max_bytes: int = 5_000_000
    # Seconds between two requests to one host when the source sets no rate_limit.
    # At least 1 s (collectors.http.MIN_DELAY_SECONDS).
    default_rate_limit: float = Field(default=5.0, ge=1.0)
    # A source_run still "running" after this many minutes, with no worker holding
    # its source's lock, is marked failed ("worker stopped").
    stale_run_minutes: int = Field(default=120, ge=1)
    # Cron (UTC) for sources whose schedule is NULL: 04:00 UTC = 06:00 Africa/Kigali.
    default_source_schedule: str = "0 4 * * *"
    # Profile backfills (worker/backfills.py): at most this many profiles scored per
    # worker tick, and a failing one is given up (logged) after this many attempts.
    backfill_per_tick: int = Field(default=5, ge=1)
    backfill_max_attempts: int = Field(default=6, ge=1)

    # Models (decision 14)
    model_extract: str = "claude-haiku-5-5"
    model_score: str = "claude-haiku-5-5"
    model_digest: str = "claude-opus-5-5"

    # Third-party keys (no BK_ prefix)
    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_API_KEY")
    )
    voyage_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("VOYAGE_API_KEY")
    )
    brave_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("BRAVE_API_KEY")
    )
    resend_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("RESEND_API_KEY")
    )

    @field_validator("unsubscribe_secret")
    @classmethod
    def _real_secret(cls, v: SecretStr | None) -> SecretStr | None:
        """Refuse example values and weak strings at startup (not only when a
        digest is sent)."""
        if v is not None and (problem := secret_problem(v.get_secret_value())):
            raise ValueError(f"BK_UNSUBSCRIBE_SECRET {problem}; {GENERATE_HINT}")
        return v

    @field_validator("database_url")
    @classmethod
    def _real_database_password(cls, v: str) -> str:
        """Refuse a database URL that still carries the example password."""
        from sqlalchemy.engine import make_url
        from sqlalchemy.exc import ArgumentError

        try:
            password = make_url(v).password
        except ArgumentError:
            return v  # not a URL; the engine reports it when connecting
        if password and (problem := placeholder_problem(str(password))):
            raise ValueError(
                f"BK_DATABASE_URL: the password {problem}; set POSTGRES_PASSWORD "
                "to a real password and use it here"
            )
        return v

    @field_validator(
        "unsubscribe_secret",
        "api_public_url",
        "unsubscribe_mailto",
        "resend_api_key",
        mode="before",
    )
    @classmethod
    def _empty_is_unset(cls, v: object) -> object:
        """An empty variable in .env means "not set"."""
        return None if isinstance(v, str) and not v.strip() else v


# Variables that no longer set anything, with what to use instead.
IGNORED_ENV = {"BK_PUBLIC_BASE_URL": "BK_WEB_BASE_URL"}

log = logging.getLogger("blackkite.config")


def ignored_env_present(env_file: str | Path | None = ".env") -> list[str]:
    """Names from IGNORED_ENV set in the process environment or in env_file."""
    file_vars = dotenv_values(env_file) if env_file and Path(env_file).is_file() else {}
    return [name for name in IGNORED_ENV if name in os.environ or name in file_vars]


def warn_ignored_env(env_file: str | Path | None = ".env") -> list[str]:
    """Log a warning for each ignored variable present; return their names."""
    found = ignored_env_present(env_file)
    for name in found:
        log.warning("%s is set but ignored; use %s", name, IGNORED_ENV[name])
    return found


def user_agent(settings: Settings) -> str:
    """Honest User-Agent for every collector request."""
    if settings.bot_contact_url:
        return f"BlackkiteBot/0.1 (+{settings.bot_contact_url})"
    return "BlackkiteBot/0.1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
