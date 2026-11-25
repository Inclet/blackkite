"""Refusals on the admin source routes in plain language (spec 4.3).

Every 422 (and the 409s that are about a field) answers::

    {"detail": "Feed URL: address 127.0.0.1 is not public.",
     "errors": [{"field": "config.feed_url",
                 "message": "address 127.0.0.1 is not public"}]}

``detail`` is what the admin reads (field names in the admin's words, no
Pydantic boilerplate, no URLs); ``errors`` is for the web to place each message
next to its field (``RefusalOut`` / ``FieldErrorOut`` in source_schemas).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from blackkite.collectors.problems import (
    ConfigInvalid,
    FieldValueError,
    Problem,
    from_error,
    sentences,
)

_LOC_ROOTS = ("body", "query", "path", "header", "cookie")


class Refusal(Exception):
    """Raise in an admin source route to refuse with field problems.
    ``extra`` keys are added to the body (e.g. the promotion gate's numbers)."""

    def __init__(
        self,
        status_code: int,
        problems: Sequence[Problem],
        *,
        detail: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.problems = list(problems)
        self.detail = detail or sentences(self.problems)
        self.extra = extra or {}
        super().__init__(self.detail)

    @classmethod
    def from_error(cls, status_code: int, e: Exception) -> Refusal:
        """From a FieldValueError/ConfigInvalid (or any message)."""
        if isinstance(e, FieldValueError | ConfigInvalid):
            return cls(status_code, e.problems)
        return cls(status_code, [Problem((), str(e))])


def request_problems(errors: Sequence[dict[str, Any]]) -> list[Problem]:
    out: list[Problem] = []
    for err in errors:
        loc = tuple(err.get("loc") or ())
        if loc and loc[0] in _LOC_ROOTS:
            loc = loc[1:]
        out.extend(from_error({**err, "loc": loc}))
    return out


def refusal_response(r: Refusal) -> JSONResponse:
    body = {
        "detail": r.detail,
        "errors": [{"field": p.field, "message": p.message} for p in r.problems],
        **r.extra,
    }
    return JSONResponse(body, status_code=r.status_code)


class RefusalRoute(APIRoute):
    """Route class for the admin source router: request-validation errors and
    ``Refusal`` become the plain body above."""

    def get_route_handler(self) -> Callable[[Request], Any]:
        handle = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await handle(request)
            except RequestValidationError as e:
                return refusal_response(Refusal(422, request_problems(e.errors())))
            except Refusal as e:
                return refusal_response(e)

        return handler
