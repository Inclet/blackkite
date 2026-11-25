"""Model clients behind small interfaces: structured LLM calls and embeddings.

Real clients: ``AnthropicLLM`` (Claude API, decision 14) and ``VoyageEmbedder``
(decision 12). Tests use fakes; nothing here is called without an API key.
"""

from blackkite.llm.client import LLMClient, LLMError
from blackkite.llm.embeddings import Embedder, EmbeddingError

__all__ = ["Embedder", "EmbeddingError", "LLMClient", "LLMError"]
