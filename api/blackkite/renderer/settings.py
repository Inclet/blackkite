"""Renderer service settings (decision 46). Process environment only: no .env
file is read, so a developer's .env with database credentials and API keys is
never loaded into the renderer.

The renderer holds no secrets other than its caller token. It refuses to start
when any variable in ``FORBIDDEN_ENV`` is present in its environment (even
empty): the container must be started without them.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from blackkite.collectors.browser_list import RenderLimits
from blackkite.collectors.http import MIN_DELAY_SECONDS
from blackkite.config import GENERATE_HINT, secret_problem

# Secrets the renderer must never hold. The brief's list (database, model and
# search keys, mail keys, the unsubscribe secret, the ingest mailbox password)
# plus the two other passwords the deploy .env carries.
FORBIDDEN_ENV = (
    "BK_DATABASE_URL",
    "ANTHROPIC_API_KEY",
    "VOYAGE_API_KEY",
    "BRAVE_API_KEY",
    "RESEND_API_KEY",
    "BK_UNSUBSCRIBE_SECRET",
    "BK_CALENDAR_SECRET",
    "BK_INGEST_IMAP_PASSWORD",
    "BK_SMTP_PASSWORD",
    "POSTGRES_PASSWORD",
)


class RendererConfigError(Exception):
    """The renderer must not start with this environment."""


def forbidden_present(environ: Mapping[str, str]) -> list[str]:
    """Names from FORBIDDEN_ENV present in ``environ`` (values never read out)."""
    return [name for name in FORBIDDEN_ENV if name in environ]


def check_environment(environ: Mapping[str, str]) -> None:
    found = forbidden_present(environ)
    if found:
        raise RendererConfigError(
            "the renderer holds no secrets; remove these variables from its "
            f"environment: {', '.join(found)}"
        )


def token_problem(value: str) -> str | None:
    """Why ``value`` cannot be the shared renderer token, or None."""
    return secret_problem(value)


class RendererSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BK_RENDERER_",
        env_file=None,
        extra="ignore",
        hide_input_in_errors=True,
    )

    # Shared with the API and worker (their BK_RENDERER_TOKEN); callers send it
    # as "Authorization: Bearer <token>". Required, at least 32 random characters.
    token: SecretStr
    # Renders at once (one headless Chromium each); more wait up to
    # queue_wait_seconds, then get 503.
    max_concurrent: int = Field(default=2, ge=1, le=8)
    queue_wait_seconds: float = Field(default=30.0, gt=0, le=300)
    # Ceilings for every render. A caller may ask for less, never more.
    timeout_seconds: float = Field(default=45.0, gt=0, le=300)
    max_bytes: int = Field(default=5_000_000, ge=1000)
    total_bytes: int = Field(default=20_000_000, ge=1000)
    max_requests: int = Field(default=150, ge=1, le=1000)
    request_timeout: float = Field(default=20.0, gt=0, le=120)
    # Floor for the pause between two requests to one host inside a render.
    subresource_delay: float = Field(default=0.25, ge=0)
    # Floor for the pause between two renders of pages on one host, whatever
    # the caller paced (robots.txt Crawl-delay raises it).
    min_host_delay: float = Field(default=MIN_DELAY_SECONDS, ge=MIN_DELAY_SECONDS)
    # A render that would have to wait longer than this for its host's turn is
    # refused ("rate_limited") rather than held.
    max_pace_wait_seconds: float = Field(default=30.0, ge=0)
    # Same variable as the API's: goes in the User-Agent.
    bot_contact_url: str | None = Field(
        default=None, validation_alias=AliasChoices("BK_BOT_CONTACT_URL")
    )

    @field_validator("token")
    @classmethod
    def _real_token(cls, v: SecretStr) -> SecretStr:
        if problem := token_problem(v.get_secret_value()):
            raise ValueError(f"BK_RENDERER_TOKEN {problem}; {GENERATE_HINT}")
        return v

    def ceiling(self) -> RenderLimits:
        return RenderLimits(
            timeout_seconds=self.timeout_seconds,
            max_bytes=self.max_bytes,
            total_bytes=self.total_bytes,
            max_requests=self.max_requests,
            subresource_delay=self.subresource_delay,
            request_timeout=self.request_timeout,
        )

    def user_agent(self) -> str:
        if self.bot_contact_url:
            return f"BlackkiteBot/0.1 (+{self.bot_contact_url})"
        return "BlackkiteBot/0.1"
