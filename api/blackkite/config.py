"""Settings, read from environment variables (prefix BK_) or a .env file.

Third-party API keys keep their conventional names without the prefix
(ANTHROPIC_API_KEY, VOYAGE_API_KEY, BRAVE_API_KEY).
"""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Dimension of opportunity.embedding. Voyage AI embedding models (decision 12)
# return 1024-dimensional vectors by default. Changing this needs a migration
# that alters the column type, and every stored embedding must be recomputed.
EMBEDDING_DIM = 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BK_", env_file=".env", extra="ignore")

    # Database (SQLAlchemy URL, psycopg 3 driver)
    database_url: str = "postgresql+psycopg://blackkite:blackkite@localhost:5432/blackkite"

    # Public URL that magic links point at (the web app, which proxies /auth to the API)
    public_base_url: str = "http://localhost:8000"
    # Where /auth/verify redirects after a successful sign-in
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

    # Mail
    mail_transport: Literal["console", "smtp"] = "console"
    mail_from: str = "Blackkite <no-reply@example.com>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False

    # Bootstrap
    first_admin_email: str | None = None

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
