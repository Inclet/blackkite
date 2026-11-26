"""FastAPI application."""

from fastapi import FastAPI

from blackkite import logredact
from blackkite.auth.ratelimit import (
    LinkRequestLimiter,
    SlidingWindowLimiter,
    UnsubscribeLimiter,
)
from blackkite.config import Settings, get_settings, warn_ignored_env
from blackkite.routes import (
    admin,
    auth,
    calendar,
    catalogue,
    digest_settings,
    items,
    member,
    profiles,
    sources,
    unsubscribe,
)
from blackkite.sources.testrun import TestRunGate

API_PREFIX = "/api"


def create_app(settings: Settings | None = None) -> FastAPI:
    # Link tokens in query strings (calendar feed, unsubscribe) never reach logs.
    logredact.install()
    warn_ignored_env()
    app = FastAPI(title="Blackkite API", version="0.1.0")
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings
    settings = settings or get_settings()
    app.state.link_limiter = LinkRequestLimiter(
        per_email=settings.link_rate_per_email_per_hour,
        per_ip=settings.link_rate_per_ip_per_hour,
    )
    # One-click unsubscribe (no session): per token, with a per-address ceiling.
    app.state.unsubscribe_limiter = UnsubscribeLimiter(
        per_token=settings.unsubscribe_rate_per_token_per_hour,
        per_ip=settings.unsubscribe_rate_per_ip_per_hour,
    )
    # Calendar feed (no session): per link, keyed by the token's hash.
    app.state.calendar_limiter = SlidingWindowLimiter(
        settings.calendar_rate_per_token_per_hour
    )
    # Admin test runs in flight at once (every collector type counts).
    app.state.test_run_gate = TestRunGate(settings.test_runs_max_concurrent)
    app.include_router(auth.router)
    # Every member and admin API route lives under /api so no API path collides
    # with a web page (docs/api-contract.md section 2): admin routes are
    # /api/admin/*, since /admin/* are the admin screens. /auth/* and GET /me
    # keep their paths.
    app.include_router(admin.router, prefix=API_PREFIX)
    app.include_router(sources.member_router, prefix=API_PREFIX)
    app.include_router(sources.admin_router, prefix=API_PREFIX)
    app.include_router(member.router, prefix=API_PREFIX)
    app.include_router(calendar.router, prefix=API_PREFIX)
    app.include_router(calendar.feed_router, prefix=API_PREFIX)
    app.include_router(items.router, prefix=API_PREFIX)
    app.include_router(catalogue.router, prefix=API_PREFIX)
    app.include_router(profiles.router, prefix=API_PREFIX)
    app.include_router(digest_settings.router, prefix=API_PREFIX)
    app.include_router(unsubscribe.router, prefix=API_PREFIX)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
