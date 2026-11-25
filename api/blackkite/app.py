"""FastAPI application."""

from fastapi import FastAPI

from blackkite.auth.ratelimit import LinkRequestLimiter, SlidingWindowLimiter
from blackkite.config import Settings, get_settings, warn_ignored_env
from blackkite.routes import (
    admin,
    auth,
    catalogue,
    digest_settings,
    member,
    profiles,
    sources,
    unsubscribe,
)

API_PREFIX = "/api"


def create_app(settings: Settings | None = None) -> FastAPI:
    warn_ignored_env()
    app = FastAPI(title="Blackkite API", version="0.1.0")
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings
    settings = settings or get_settings()
    app.state.link_limiter = LinkRequestLimiter(
        per_email=settings.link_rate_per_email_per_hour,
        per_ip=settings.link_rate_per_ip_per_hour,
    )
    # One-click unsubscribe (no session): per client address, like link requests.
    app.state.unsubscribe_limiter = SlidingWindowLimiter(
        settings.link_rate_per_ip_per_hour
    )
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(sources.member_router, prefix=API_PREFIX)
    app.include_router(sources.admin_router)
    # Phase 4 member routes (and the admin catalogue) live under /api so no API
    # path collides with a web page (docs/api-contract.md section 2). /auth/*,
    # GET /me and the earlier /admin/* routes keep their paths.
    app.include_router(member.router, prefix=API_PREFIX)
    app.include_router(catalogue.router, prefix=API_PREFIX)
    app.include_router(profiles.router, prefix=API_PREFIX)
    app.include_router(digest_settings.router, prefix=API_PREFIX)
    app.include_router(unsubscribe.router, prefix=API_PREFIX)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
