"""Build the real clients from settings. ``None`` when the key is not set."""

from __future__ import annotations

from blackkite.config import EMBEDDING_DIM, Settings
from blackkite.llm.client import LLMClient
from blackkite.llm.embeddings import Embedder
from blackkite.pipeline.settings import PipelineSettings


def extraction_llm(settings: Settings, pipeline: PipelineSettings) -> LLMClient | None:
    if (
        settings.anthropic_api_key is None
        or not settings.anthropic_api_key.get_secret_value()
    ):
        return None
    from blackkite.llm.anthropic_client import AnthropicLLM

    return AnthropicLLM(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.model_extract,
        timeout_seconds=pipeline.llm_timeout_seconds,
    )


def embedder(settings: Settings, pipeline: PipelineSettings) -> Embedder | None:
    if (
        settings.voyage_api_key is None
        or not settings.voyage_api_key.get_secret_value()
    ):
        return None
    from blackkite.llm.embeddings import VoyageEmbedder

    return VoyageEmbedder(
        api_key=settings.voyage_api_key.get_secret_value(),
        model=pipeline.embedding_model,
        dim=EMBEDDING_DIM,
    )
