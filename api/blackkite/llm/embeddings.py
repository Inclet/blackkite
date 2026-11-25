"""Embedding interface and the Voyage AI implementation (decision 12).

Item text is sent to Voyage; nothing else is. Vectors must have EMBEDDING_DIM
dimensions to fit opportunity.embedding.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from blackkite.config import EMBEDDING_DIM

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"


class EmbeddingError(Exception):
    pass


class Embedder(Protocol):
    @property
    def model(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class VoyageEmbedder:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dim: int = EMBEDDING_DIM,
        timeout_seconds: float = 30.0,
        http: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dim = dim
        self._http = http or httpx.Client(timeout=timeout_seconds)

    @property
    def model(self) -> str:
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            resp = self._http.post(
                VOYAGE_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "input": texts,
                    "input_type": "document",
                    "output_dimension": self._dim,
                },
            )
            resp.raise_for_status()
            data = resp.json()["data"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise EmbeddingError(f"{type(exc).__name__}: {exc}") from exc
        vectors = [row["embedding"] for row in sorted(data, key=lambda r: r["index"])]
        if len(vectors) != len(texts) or any(len(v) != self._dim for v in vectors):
            raise EmbeddingError(
                f"expected {len(texts)} vectors of {self._dim} dimensions"
            )
        return vectors
