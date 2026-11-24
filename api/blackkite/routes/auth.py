"""Sign-in endpoints (spec 9) and /me."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from blackkite.auth import service
from blackkite.auth.deps import CurrentUser, DbDep, SettingsDep, get_link_limiter
from blackkite.auth.ratelimit import LinkRequestLimiter
from blackkite.auth.tokens import hash_token
from blackkite.db.models import Session
from blackkite.delivery.mail import MailTransport, get_mail_transport
from blackkite.routes.schemas import EmailIn, Message, TokenIn, UserOut, VerifyOut

router = APIRouter()

LINK_SENT = "If this address can sign in, a link is on its way."
INVALID_LINK = "This link is invalid or has expired. Request a new one."


@router.post("/auth/request-link", status_code=202, response_model=Message)
def request_link(
    body: EmailIn,
    request: Request,
    background: BackgroundTasks,
    db: DbDep,
    settings: SettingsDep,
    limiter: Annotated[LinkRequestLimiter, Depends(get_link_limiter)],
    mailer: Annotated[MailTransport, Depends(get_mail_transport)],
) -> Message:
    email = service.normalise_email(body.email)
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(email, ip):
        raise HTTPException(429, "Too many sign-in requests. Try again later.")
    mail = service.issue_login_link(db, settings, email)
    db.commit()
    if mail is not None:
        # Sent after the response so known and unknown addresses answer in similar time.
        background.add_task(mailer.send, mail)
    return Message(detail=LINK_SENT)


@router.post("/auth/verify", response_model=VerifyOut)
def verify(body: TokenIn, request: Request, db: DbDep, settings: SettingsDep) -> Response:
    """Spend a sign-in or invite token and start a session (decision 17).

    Called by the web confirm page (/auth/confirm) when the person presses
    "Continue to sign in". There is no GET: opening the emailed link must not spend
    the token, and a token in a request body stays out of access logs. JSON only,
    so a cross-site form cannot post here without a CORS preflight.
    """
    ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype != "application/json":
        raise HTTPException(415, "Send the token as JSON.")
    user = service.consume_token(db, body.token)
    if user is None:
        db.commit()  # keep the token spent even if sign-in fails
        return JSONResponse({"detail": INVALID_LINK}, status_code=400,
                            headers={"Cache-Control": "no-store"})
    raw = service.create_session(db, settings, user)
    db.commit()
    resp = JSONResponse({"redirect": settings.after_login_url})
    resp.set_cookie(
        settings.session_cookie_name,
        raw,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.post("/auth/logout", status_code=204)
def logout(request: Request, db: DbDep, settings: SettingsDep) -> Response:
    raw = request.cookies.get(settings.session_cookie_name)
    if raw:
        db.query(Session).filter(Session.token_hash == hash_token(raw)).delete()
        db.commit()
    resp = Response(status_code=204)
    resp.delete_cookie(
        settings.session_cookie_name, path="/", httponly=True,
        secure=settings.cookie_secure, samesite="lax",
    )
    return resp


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
