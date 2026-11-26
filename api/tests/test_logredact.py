"""Link tokens are redacted from logs (calendar feed, unsubscribe)."""

from __future__ import annotations

import io
import logging

from uvicorn.logging import AccessFormatter

from blackkite import logredact
from blackkite.logredact import TokenRedactFilter, redact


def test_redact_rewrites_token_values_only():
    assert (
        redact("GET /api/calendar.ics?token=abc-_123%3D&x=1 HTTP/1.1")
        == "GET /api/calendar.ics?token=[redacted]&x=1 HTTP/1.1"
    )
    assert redact("/api/unsubscribe?a=1&Token=zz#f") == (
        "/api/unsubscribe?a=1&Token=[redacted]#f"
    )
    assert redact("/api/feed?stream=tender") == "/api/feed?stream=tender"


def _record(msg, args, name="uvicorn.access"):
    return logging.LogRecord(name, logging.INFO, __file__, 1, msg, args, None)


def test_filter_keeps_uvicorn_access_args_usable():
    rec = _record(
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "POST", "/api/unsubscribe?token=s3cret", "1.1", 200),
    )
    assert TokenRedactFilter().filter(rec) is True
    out = AccessFormatter(
        '%(client_addr)s - "%(request_line)s" %(status_code)s'
    ).format(rec)
    assert "s3cret" not in out
    assert "/api/unsubscribe?token=[redacted]" in out and "200" in out


def test_filter_handles_message_and_dict_args():
    rec = _record("fetched %(url)s", ({"url": "https://x/api/calendar.ics?token=t0k"},))
    TokenRedactFilter().filter(rec)
    assert rec.getMessage() == "fetched https://x/api/calendar.ics?token=[redacted]"
    rec = _record("link /api/calendar.ics?token=t0k", None, name="blackkite")
    TokenRedactFilter().filter(rec)
    assert "t0k" not in rec.getMessage()


def test_install_covers_uvicorn_access_and_app_loggers():
    access = logging.getLogger("uvicorn.access")
    root = logging.getLogger()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    root.addHandler(handler)
    old_level, old_prop = access.level, access.propagate
    try:
        logredact.install()
        logredact.install()  # idempotent
        assert sum(isinstance(f, TokenRedactFilter) for f in access.filters) == 1
        assert any(isinstance(f, TokenRedactFilter) for f in handler.filters)
        access.setLevel(logging.INFO)
        access.propagate = True
        access.info(
            '%s - "%s %s HTTP/%s" %d',
            "1.2.3.4:5",
            "GET",
            "/api/calendar.ics?token=s3cret",
            "1.1",
            200,
        )
        app_log = logging.getLogger("blackkite.delivery")
        app_log.warning("bad link %s", "/api/unsubscribe?token=s3cret")
        text = stream.getvalue()
        assert "s3cret" not in text
        assert text.count("token=[redacted]") == 2
    finally:
        root.removeHandler(handler)
        access.setLevel(old_level)
        access.propagate = old_prop


def test_app_installs_the_filter(app):
    assert any(
        isinstance(f, TokenRedactFilter)
        for f in logging.getLogger("uvicorn.access").filters
    )
