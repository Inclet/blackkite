"""Personal calendar feed links (docs/api-contract.md section 5).

``GET /api/calendar.ics?token=...`` needs no session: calendar apps fetch it on
their own. The token is the authority, built like the unsubscribe tokens
(delivery/unsubscribe.py) but with its own secret, context and nonce:
``base64url(version | user id | calendar_nonce | mac)``, the MAC an
HMAC-SHA256 over the rest keyed with ``BK_CALENDAR_SECRET``, truncated to 16
bytes. Rotating the user's ``calendar_nonce`` (``rotate``) revokes the link;
changing the secret revokes everyone's. Unsubscribe links are untouched by
either.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from blackkite.config import GENERATE_HINT, Settings, secret_problem
from blackkite.db.models import User, new_unsubscribe_nonce

_VERSION = b"\x01"
_CONTEXT = b"blackkite-calendar-feed\x00"
_MAC_BYTES = 16
_TOKEN_BYTES = 1 + 16 + 16 + _MAC_BYTES
FEED_PATH = "/api/calendar.ics"


class CalendarNotConfigured(RuntimeError):
    """BK_CALENDAR_SECRET is not set (or not usable)."""


def _secret(settings: Settings) -> bytes:
    if settings.calendar_secret is None:
        raise CalendarNotConfigured("BK_CALENDAR_SECRET is not set")
    value = settings.calendar_secret.get_secret_value()
    if problem := secret_problem(value):
        raise CalendarNotConfigured(f"BK_CALENDAR_SECRET {problem}; {GENERATE_HINT}")
    return value.encode()


def configured(settings: Settings) -> bool:
    try:
        _secret(settings)
    except CalendarNotConfigured:
        return False
    return True


def _mac(secret: bytes, data: bytes) -> bytes:
    return hmac.new(secret, _CONTEXT + data, hashlib.sha256).digest()[:_MAC_BYTES]


def make_token(settings: Settings, user: User) -> str:
    data = _VERSION + user.id.bytes + bytes.fromhex(user.calendar_nonce)
    raw = data + _mac(_secret(settings), data)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def feed_url(settings: Settings, user: User) -> str:
    api = (settings.api_public_url or settings.web_base_url).rstrip("/")
    return f"{api}{FEED_PATH}?token={make_token(settings, user)}"


def webcal_url(url: str) -> str:
    """The same link with the webcal scheme, which calendar apps subscribe to."""
    return "webcal://" + url.split("://", 1)[1]


def user_for_token(db: Session, settings: Settings, token: str) -> User | None:
    """The active user the token belongs to, or None (bad signature, revoked,
    unknown or deactivated user)."""
    if not isinstance(token, str) or not 60 <= len(token) <= 100:
        return None
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except (binascii.Error, ValueError):
        return None
    if len(raw) != _TOKEN_BYTES or raw[:1] != _VERSION:
        return None
    data, mac = raw[:-_MAC_BYTES], raw[-_MAC_BYTES:]
    if not hmac.compare_digest(mac, _mac(_secret(settings), data)):
        return None
    user = db.get(User, uuid.UUID(bytes=data[1:17]))
    if user is None or user.status != "active":
        return None
    if not hmac.compare_digest(
        user.calendar_nonce.encode(), data[17:33].hex().encode()
    ):
        return None
    return user


def rotate(user: User, now: datetime) -> None:
    """Revoke the user's calendar link; the caller commits."""
    user.calendar_nonce = new_unsubscribe_nonce()
    user.calendar_nonce_rotated_at = now
