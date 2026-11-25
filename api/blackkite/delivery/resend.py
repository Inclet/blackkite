"""Mail through Resend's HTTP API (decision 45).

Selected with ``BK_MAIL_TRANSPORT=resend``. Needs ``RESEND_API_KEY`` (from the
environment only) and an explicit ``BK_MAIL_FROM``. No real email goes out
until the owner gives the go-ahead: while ``BK_MAIL_ALLOW_REAL_SEND`` is false
(the default) the transport refuses every send and raises ``RealSendDisabled``
carrying what it would have sent (sender, recipient, subject, sizes, header
names; never the body, the header values or the key), so callers do not record
the mail as sent and log it (the worker once per user per kind per day).

Request, as understood from Resend's public API documentation (field names NOT
verified against the live API; check before the first real send)::

    POST https://api.resend.com/emails
    Authorization: Bearer <RESEND_API_KEY>
    Content-Type: application/json

    {"from": "...", "to": ["..."], "subject": "...", "html": "...", "text": "...",
     "headers": {"List-Unsubscribe": "...", ...},
     "attachments": [{"filename": "kite.png", "content": "<base64>",
                      "content_type": "image/png", "content_id": "kite-logo"}]}

A 2xx answer carries ``{"id": "..."}``. Anything else raises ``ResendError``;
there is no retry here (spec 10: never retry aggressively).
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from blackkite.config import Settings
from blackkite.delivery.mail import Mail

log = logging.getLogger("blackkite.mail")

RESEND_EMAILS_URL = "https://api.resend.com/emails"
TIMEOUT_SECONDS = 15.0


class ResendError(RuntimeError):
    """Resend did not accept the message."""


class RealSendDisabled(RuntimeError):
    """BK_MAIL_ALLOW_REAL_SEND is false, so nothing was sent."""


class ResendNotConfigured(ValueError):
    """The resend transport was selected without its key or sender."""


def payload(mail: Mail, sender: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "from": sender,
        "to": [mail.to],
        "subject": mail.subject,
        "text": mail.text,
    }
    if mail.html is not None:
        body["html"] = mail.html
        if mail.inline:
            body["attachments"] = [
                {
                    "filename": img.filename,
                    "content": base64.b64encode(img.data).decode("ascii"),
                    "content_type": f"image/{img.subtype}",
                    "content_id": img.cid,
                }
                for img in mail.inline
            ]
    if mail.headers:
        body["headers"] = dict(mail.headers)
    return body


class ResendTransport:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if settings.resend_api_key is None:
            raise ResendNotConfigured("BK_MAIL_TRANSPORT=resend needs RESEND_API_KEY")
        if "mail_from" not in settings.model_fields_set or not settings.mail_from:
            raise ResendNotConfigured("BK_MAIL_TRANSPORT=resend needs BK_MAIL_FROM")
        self._key = settings.resend_api_key
        self.sender = settings.mail_from
        self.allow_real_send = settings.mail_allow_real_send
        self._client = client

    def _describe(self, mail: Mail) -> str:
        return (
            f"from={self.sender!r} to={mail.to!r} subject={mail.subject!r} "
            f"text={len(mail.text)} chars html="
            f"{len(mail.html) if mail.html is not None else 0} chars "
            f"inline={[i.cid for i in mail.inline]} "
            f"headers={[name for name, _ in mail.headers]}"
        )

    def send(self, mail: Mail) -> None:
        if not self.allow_real_send:
            # The description travels in the exception; the worker logs it once
            # per user per kind per day (delivery/jobs.py), other callers log it.
            raise RealSendDisabled(
                "BK_MAIL_ALLOW_REAL_SEND is false; nothing sent; would have sent "
                + self._describe(mail)
            )
        client = self._client or httpx.Client(timeout=TIMEOUT_SECONDS)
        try:
            r = client.post(
                RESEND_EMAILS_URL,
                json=payload(mail, self.sender),
                headers={
                    "Authorization": f"Bearer {self._key.get_secret_value()}",
                    "User-Agent": "Blackkite/0.1",
                },
            )
        except httpx.HTTPError as exc:
            raise ResendError(f"resend: request failed: {type(exc).__name__}") from None
        finally:
            if self._client is None:
                client.close()
        if not 200 <= r.status_code < 300:
            raise ResendError(f"resend: HTTP {r.status_code}: {r.text[:300]}")
        log.info("resend: sent %s id=%s", self._describe(mail), _id(r))


def _id(r: httpx.Response) -> str | None:
    try:
        data = r.json()
    except ValueError:
        return None
    return data.get("id") if isinstance(data, dict) else None
