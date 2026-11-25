"""The structured-output LLM interface the pipeline depends on."""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """The model call failed or its reply did not match the schema."""


class LLMClient(Protocol):
    """One call in, one validated Pydantic object out."""

    @property
    def model(self) -> str: ...

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        tool_name: str,
        tool_description: str,
    ) -> T: ...
