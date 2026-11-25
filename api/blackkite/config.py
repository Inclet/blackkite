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

# Dimension of opportunity.embedding. Voyage AI embedding models (decision 12)
# return 1024-dimensional vectors by default. Changing this needs a migration
# that alters the column type, and every stored embedding must be recomputed.
EMBEDDING_DIM = 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BK_", env_file=".env", extra="ignore")

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
    unsubscribe_secret: SecretStr | None = Field(default=None, min_length=32)
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
