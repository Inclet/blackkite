"""Keep link tokens out of logs.

The calendar feed (``/api/calendar.ics?token=…``) and one-click unsubscribe
(``/api/unsubscribe?token=…``, GET and POST) carry their secret in the query
string, so uvicorn's access log would write it in full. ``TokenRedactFilter``
rewrites every ``token=<value>`` in a record's message and arguments to
``token=[redacted]``, keeping the argument tuple's shape (uvicorn's access
formatter unpacks it). ``install()`` puts it on uvicorn's loggers and on every
handler already configured, so app loggers that propagate to the root are
covered too. The reverse proxy in front of the API must redact its own access
log the same way (see .env.example).
"""

from __future__ import annotations

import logging
import re
from typing import Any

# token=… up to the next query separator, fragment, space or quote. Also
# matches longer names ending in "token" (csrf_token=…), which is wanted.
TOKEN_RE = re.compile(r"(token=)[^&\s#\"']*", re.IGNORECASE)
REDACTED = r"\1[redacted]"

UVICORN_LOGGERS = ("uvicorn", "uvicorn.access", "uvicorn.error")


def redact(text: str) -> str:
    return TOKEN_RE.sub(REDACTED, text)


def _arg(v: Any) -> Any:
    if isinstance(v, str):
        return redact(v)
    if v is None or isinstance(v, (int, float, bool)):
        return v
    text = str(v)
    redacted = redact(text)
    return redacted if redacted != text else v


class TokenRedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_arg(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: _arg(v) for k, v in record.args.items()}
        return True


_FILTER = TokenRedactFilter()


def _add(target: logging.Filterer) -> None:
    if not any(isinstance(f, TokenRedactFilter) for f in target.filters):
        target.addFilter(_FILTER)


def install() -> None:
    """Idempotent. Call after logging is configured (uvicorn configures it
    before importing the app; the worker after basicConfig)."""
    loggers = [logging.getLogger(), *(logging.getLogger(n) for n in UVICORN_LOGGERS)]
    for lg in loggers:
        _add(lg)
        for h in lg.handlers:
            _add(h)
