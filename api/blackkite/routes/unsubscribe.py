"""One-click unsubscribe (decision 43; docs/api-contract.md section 2).

``POST /api/unsubscribe`` needs no session: the signed token is the authority
(delivery/unsubscribe.py). It takes either

* ``{"token": "..."}`` as JSON, from the web page ``/unsubscribe`` (which reads
  the token from its URL fragment), or
* the RFC 8058 one-click POST a mail client sends for the List-Unsubscribe
  header: the token in the query string and the form body
  ``List-Unsubscribe=One-Click`` (urlencoded or multipart).

A digest token sets the digest frequency to "off"; an alert token turns alerts
off (alert_min_fit null). Repeating it changes nothing more. ``GET`` changes
nothing (link scanners open URLs): it only says to use POST. Requests are
rate-limited per token (keyed by its hash), so one-click POSTs from a mail
provider's shared addresses are not blocked, with a generous per-address
ceiling against floods.
"""

from __future__ import annotations

import json
from email.parser import BytesParser
from email.policy import HTTP
from typing import Annotated, Literal
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from blackkite.auth.deps import DbDep, SettingsDep
from blackkite.auth.ratelimit import UnsubscribeLimiter
from blackkite.delivery import unsubscribe as U
from blackkite.member.schemas import CamelModel

router = APIRouter()

DONE = "You won't get these emails any more."
INVALID = "This unsubscribe link is not valid. Change your emails in settings."
USE_POST = "Use POST to unsubscribe. Opening this link changes nothing."
MAX_BODY = 4096
TOO_MANY = "Too many requests. Try again later."
NO_STORE = {"Cache-Control": "no-store"}


class UnsubscribeOut(CamelModel):
    kind: Literal["digest", "alert"]
    detail: str


def get_unsubscribe_limiter(request: Request) -> UnsubscribeLimiter:
    return request.app.state.unsubscribe_limiter


def _form_fields(ctype: str, raw: bytes) -> dict[str, list[str]]:
    media = ctype.split(";")[0].strip().lower()
    if media == "application/x-www-form-urlencoded":
        return parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True)
    if media == "multipart/form-data":
        msg = BytesParser(policy=HTTP).parsebytes(
            f"Content-Type: {ctype}\r\n\r\n".encode() + raw
        )
        out: dict[str, list[str]] = {}
        if msg.is_multipart():
            for part in msg.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if isinstance(name, str):
                    payload = part.get_payload(decode=True) or b""
                    out.setdefault(name, []).append(payload.decode("utf-8", "replace"))
        return out
    raise HTTPException(415, "Send JSON {token} or the one-click form.")


async def _token(request: Request, query_token: str | None) -> str:
    ctype = request.headers.get("content-type", "")
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "Request too large.")
    if ctype.split(";")[0].strip().lower() == "application/json":
        try:
            body = json.loads(raw)
        except ValueError:
            raise HTTPException(400, INVALID) from None
        token = body.get("token") if isinstance(body, dict) else None
        if not isinstance(token, str):
            raise HTTPException(422, "token is required.")
        return token
    fields = _form_fields(ctype, raw)
    if fields.get("List-Unsubscribe") != ["One-Click"]:
        raise HTTPException(400, "Expected List-Unsubscribe=One-Click.")
    if not query_token:
        raise HTTPException(422, "token is required.")
    return query_token


@router.post("/unsubscribe", response_model=UnsubscribeOut)
async def post_unsubscribe(
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    limiter: Annotated[UnsubscribeLimiter, Depends(get_unsubscribe_limiter)],
    token: Annotated[str | None, Query(max_length=200)] = None,
) -> JSONResponse:
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow_ip(ip):
        raise HTTPException(429, TOO_MANY)
    value = await _token(request, token)
    if not limiter.allow_token(value):
        raise HTTPException(429, TOO_MANY)

    def apply() -> str | None:
        kind = U.unsubscribe(db, settings, value)
        if kind is None:
            db.rollback()
        else:
            db.commit()
        return kind

    kind = await run_in_threadpool(apply)
    if kind is None:
        return JSONResponse({"detail": INVALID}, status_code=400, headers=NO_STORE)
    out = UnsubscribeOut(kind=kind, detail=DONE)  # type: ignore[arg-type]
    return JSONResponse(out.model_dump(by_alias=True), headers=NO_STORE)


@router.get("/unsubscribe", include_in_schema=False)
def get_unsubscribe() -> JSONResponse:
    return JSONResponse(
        {"detail": USE_POST},
        status_code=405,
        headers={"Allow": "POST", **NO_STORE},
    )
