"""FastAPI dependencies for authentication and roles. Checks run on the server."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DB

from blackkite.auth.ratelimit import LinkRequestLimiter
from blackkite.auth.service import session_user
from blackkite.config import Settings, get_settings
from blackkite.db.models import User
from blackkite.db.session import get_db

DbDep = Annotated[DB, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def require_user(request: Request, db: DbDep, settings: SettingsDep) -> User:
    raw = request.cookies.get(settings.session_cookie_name)
    found = session_user(db, raw) if raw else None
    if found is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    request.state.session = found[0]
    return found[1]


CurrentUser = Annotated[User, Depends(require_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def get_link_limiter(request: Request) -> LinkRequestLimiter:
    return request.app.state.link_limiter
