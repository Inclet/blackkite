"""One-click unsubscribe (decision 43, RFC 8058).

Every digest and alert email carries a signed link that turns that kind of email
off without signing in:

* in the body, the web page ``{web}/unsubscribe#token=...`` (token in the
  fragment, as with sign-in links, so it never reaches a server log or Referer);
  the page POSTs ``{token}`` to ``/api/unsubscribe``;
* the headers ``List-Unsubscribe: <{api}/api/unsubscribe?token=...>`` (plus a
  ``mailto:`` when one is configured) and
  ``List-Unsubscribe-Post: List-Unsubscribe=One-Click``, so a mail client can
  unsubscribe with one POST.

A token is ``base64url(version | kind | user id | nonce | mac)``: the user's id
(16 bytes), the kind ("d" digest, "a" alert), the user's ``unsubscribe_nonce``
(16 bytes) and an HMAC-SHA256 over the rest, keyed with ``BK_UNSUBSCRIBE_SECRET``
and truncated to 16 bytes. Without the secret a token cannot be made; rotating a
user's nonce (``rotate_nonce``) revokes every link sent to them before, and
changing the secret revokes everyone's.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import uuid
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

import sqlalchemy as sa
from sqlalchemy.orm import Session

from blackkite.config import Settings
from blackkite.db.models import DigestSetting, User, new_unsubscribe_nonce

Kind = Literal["digest", "alert"]

_VERSION = b"\x01"
_KIND_CODES: dict[str, bytes] = {"digest": b"d", "alert": b"a"}
_KINDS: dict[bytes, Kind] = {b"d": "digest", b"a": "alert"}
_CONTEXT = b"blackkite-unsubscribe\x00"
_MAC_BYTES = 16
_TOKEN_BYTES = 1 + 1 + 16 + 16 + _MAC_BYTES
UNSUBSCRIBE_PAGE = "/unsubscribe"
UNSUBSCRIBE_API = "/api/unsubscribe"


class UnsubscribeNotConfigured(RuntimeError):
    """BK_UNSUBSCRIBE_SECRET is not set, so no email may go out without a link."""


def _secret(settings: Settings) -> bytes:
    if settings.unsubscribe_secret is None:
        raise UnsubscribeNotConfigured(
            "BK_UNSUBSCRIBE_SECRET is not set; digests and alerts need it for "
            "their unsubscribe links"
        )
    return settings.unsubscribe_secret.get_secret_value().encode()


def _mac(secret: bytes, data: bytes) -> bytes:
    return hmac.new(secret, _CONTEXT + data, hashlib.sha256).digest()[:_MAC_BYTES]


def make_token(settings: Settings, user: User, kind: Kind) -> str:
    data = (
        _VERSION
        + _KIND_CODES[kind]
        + user.id.bytes
        + bytes.fromhex(user.unsubscribe_nonce)
    )
    raw = data + _mac(_secret(settings), data)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_id: uuid.UUID
    kind: Kind
    nonce: str


def read_token(settings: Settings, token: str) -> TokenClaims | None:
    """The token's claims if its signature is good, else None. The nonce still
    has to match the user's current one (``unsubscribe``)."""
    if not isinstance(token, str) or not 40 <= len(token) <= 100:
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
    kind = _KINDS.get(data[1:2])
    if kind is None:
        return None
    return TokenClaims(
        user_id=uuid.UUID(bytes=data[2:18]), kind=kind, nonce=data[18:34].hex()
    )


@dataclass(frozen=True, slots=True)
class UnsubscribeLinks:
    page_url: str
    headers: tuple[tuple[str, str], ...]


def links(settings: Settings, user: User, kind: Kind) -> UnsubscribeLinks:
    """The body link and the RFC 8058 headers for one email to ``user``."""
    token = make_token(settings, user, kind)
    web = settings.web_base_url.rstrip("/")
    api = (settings.api_public_url or settings.web_base_url).rstrip("/")
    targets = [f"<{api}{UNSUBSCRIBE_API}?token={token}>"]
    if settings.unsubscribe_mailto:
        subject = quote(f"unsubscribe {token}", safe="")
        targets.append(f"<mailto:{settings.unsubscribe_mailto}?subject={subject}>")
    return UnsubscribeLinks(
        page_url=f"{web}{UNSUBSCRIBE_PAGE}#token={token}",
        headers=(
            ("List-Unsubscribe", ", ".join(targets)),
            ("List-Unsubscribe-Post", "List-Unsubscribe=One-Click"),
        ),
    )


def rotate_nonce(user: User) -> None:
    """Revoke every unsubscribe link sent to this user so far."""
    user.unsubscribe_nonce = new_unsubscribe_nonce()


def unsubscribe(db: Session, settings: Settings, token: str) -> Kind | None:
    """Turn off what the token names: the weekly digest (frequency "off") or
    urgent alerts (alert_min_fit null). Idempotent. Returns the kind, or None
    when the token is not valid (bad signature, revoked, no such user).
    Does not commit."""
    claims = read_token(settings, token)
    if claims is None:
        return None
    user = db.get(User, claims.user_id)
    if user is None or not hmac.compare_digest(
        user.unsubscribe_nonce.encode(), claims.nonce.encode()
    ):
        return None
    setting = db.scalar(
        sa.select(DigestSetting).where(
            DigestSetting.user_id == user.id, DigestSetting.channel == "email"
        )
    )
    if claims.kind == "digest":
        if setting is None:
            # No row means the default (weekly to the account's address).
            setting = DigestSetting(
                user_id=user.id, channel="email", address=user.email
            )
            db.add(setting)
        setting.frequency = "off"
    elif setting is not None:
        setting.alert_min_fit = None
    db.flush()
    return claims.kind
