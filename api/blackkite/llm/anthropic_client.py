"""Claude implementation of LLMClient, using forced tool use for structured output."""

from __future__ import annotations

from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from blackkite.llm.client import LLMError

T = TypeVar("T", bound=BaseModel)


class AnthropicLLM:
    """The reply is the input of a single forced tool call, validated by ``schema``."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int = 4096,
        timeout_seconds: float = 60.0,
        client: Any | None = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        # One retry at most (spec 10: never retry aggressively).
        self._client = client or anthropic.Anthropic(
            api_key=api_key, max_retries=1, timeout=timeout_seconds
        )

    @property
    def model(self) -> str:
        return self._model

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        tool_name: str,
        tool_description: str,
    ) -> T:
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=[
                    {
                        "name": tool_name,
                        "description": tool_description,
                        "input_schema": schema.model_json_schema(),
                    }
                ],
                tool_choice={"type": "tool", "name": tool_name},
            )
        except anthropic.AnthropicError as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc
        if getattr(resp, "stop_reason", None) == "max_tokens":
            raise LLMError("reply truncated at max_tokens")
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                try:
                    return schema.model_validate(block.input)
                except ValidationError as exc:
                    raise LLMError(f"reply did not match schema: {exc}") from exc
        raise LLMError("reply had no tool call")
