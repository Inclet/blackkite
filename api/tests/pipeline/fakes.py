"""Test doubles for the model clients and the fetcher. No network."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from blackkite.config import EMBEDDING_DIM
from blackkite.llm.client import LLMError
from blackkite.pipeline.extract import ExtractionReply


class FakeLLM:
    """Returns ``reply`` (an ExtractionReply, a dict, or a callable of the user
    message) and records every call."""

    model = "fake-extract-1"

    def __init__(self, reply: Any = None, error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def structured(self, *, system, user, schema, tool_name, tool_description):
        self.calls.append({"system": system, "user": user, "tool": tool_name})
        if self.error:
            raise self.error
        reply = self.reply(user) if callable(self.reply) else self.reply
        if reply is None:
            raise LLMError("no reply configured")
        if isinstance(reply, ExtractionReply):
            return reply
        return schema.model_validate(reply)


class FakeEmbedder:
    model = "fake-embed-1"

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self.dim = dim
        self.texts: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts.extend(texts)
        return [[0.5] * self.dim for _ in texts]


class FakeFetcher:
    """Maps URL -> (content_type, bytes), or an exception to raise."""

    def __init__(self, pages: dict[str, Any] | Callable[[str], Any]) -> None:
        self.pages = pages
        self.requested: list[str] = []

    def get(self, url: str) -> tuple[str, bytes]:
        self.requested.append(url)
        page = self.pages(url) if callable(self.pages) else self.pages.get(url)
        if page is None:
            raise OSError(f"404 {url}")
        if isinstance(page, Exception):
            raise page
        return page


def q(value: Any, snippet: str | None = None) -> dict[str, Any]:
    return {"value": value, "snippet": snippet if snippet is not None else value}
