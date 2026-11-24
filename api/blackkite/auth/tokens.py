"""Random tokens and their stored form."""

import hashlib
import secrets

TOKEN_BYTES = 32  # 256 bits of randomness; ~43 url-safe characters


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """sha256 hex digest. Tokens are high-entropy, so an unsalted fast hash is enough."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
