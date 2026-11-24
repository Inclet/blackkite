"""FastAPI application."""

from fastapi import FastAPI

from blackkite.auth.ratelimit import LinkRequestLimiter
from blackkite.config import Settings, get_settings, warn_ignored_env
from blackkite.routes import admin, auth


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
    app.include_router(auth.router)
    app.include_router(admin.router)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
