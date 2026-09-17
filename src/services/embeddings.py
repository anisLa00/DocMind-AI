"""Embedding providers.

Every provider returns unit-length vectors of exactly ``EMBEDDING_DIMENSIONS``
components, so the pgvector column can stay a fixed width no matter which
provider is configured. A provider with a smaller native width is zero-padded:
padding with zeros leaves dot products - and therefore cosine similarity -
completely unchanged.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

import httpx

from src.config import settings
from src.utils.errors import EmbeddingError

_TOKEN_RE = re.compile(r"[a-z0-9']+")

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
OPENAI_URL = "https://api.openai.com/v1/embeddings"


def _normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def _fit_dimensions(vector: list[float], target: int) -> list[float]:
    if len(vector) == target:
        return vector
    if len(vector) < target:
        return vector + [0.0] * (target - len(vector))
    # Truncating drops information, so re-normalise to keep vectors comparable.
    return _normalise(vector[:target])


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Cosine similarity, safe against zero vectors and length mismatches."""
    size = min(len(left), len(right))
    if size == 0:
        return 0.0

    dot = sum(left[i] * right[i] for i in range(size))
    left_norm = math.sqrt(sum(value * value for value in left[:size]))
    right_norm = math.sqrt(sum(value * value for value in right[:size]))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0

    return dot / (left_norm * right_norm)


class BaseEmbedder:
    name = "base"

    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions or settings.EMBEDDING_DIMENSIONS

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_documents([text])
        return vectors[0]


class HashEmbedder(BaseEmbedder):
    """Deterministic local embedder - a hashing vectoriser over word n-grams.

    It captures lexical overlap only (no semantics), but it needs no API key and
    no network, which keeps the pipeline and the test suite fully runnable
    offline. Use `voyage` or `openai` when retrieval quality matters.
    """

    name = "hash"

    def _features(self, text: str) -> list[str]:
        tokens = _TOKEN_RE.findall(text.lower())
        bigrams = [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        return tokens + bigrams

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for feature in self._features(text):
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            bucket = value % self.dimensions
            # Use a spare bit as the sign so colliding features can cancel out
            # instead of always reinforcing each other.
            sign = 1.0 if (value >> 63) & 1 else -1.0
            vector[bucket] += sign
        return _normalise(vector)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]


class HTTPEmbedder(BaseEmbedder):
    """Shared client for the Voyage/OpenAI style `/embeddings` REST endpoints."""

    url = ""
    supports_input_type = False

    def __init__(self, dimensions: int | None = None) -> None:
        super().__init__(dimensions)
        if not settings.EMBEDDING_API_KEY:
            raise EmbeddingError(
                f"EMBEDDING_API_KEY is required for the '{self.name}' embedding provider"
            )
        self.endpoint = settings.EMBEDDING_BASE_URL.rstrip("/") or self.url
        if not self.endpoint.endswith("/embeddings"):
            self.endpoint = f"{self.endpoint}/embeddings"

    def _payload(self, texts: list[str], input_type: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"input": texts, "model": settings.EMBEDDING_MODEL}
        if self.supports_input_type:
            payload["input_type"] = input_type
        return payload

    async def _post(self, texts: list[str], input_type: str) -> list[list[float]]:
        headers = {
            "Authorization": f"Bearer {settings.EMBEDDING_API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=settings.EMBEDDING_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    self.endpoint, json=self._payload(texts, input_type), headers=headers
                )
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            raise EmbeddingError(
                f"{self.name} embeddings failed with HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"Could not reach the {self.name} embeddings API: {exc}") from exc

        try:
            items = sorted(body["data"], key=lambda item: item.get("index", 0))
            vectors = [list(map(float, item["embedding"])) for item in items]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingError(f"Unexpected response from {self.name} embeddings API") from exc

        if len(vectors) != len(texts):
            raise EmbeddingError(
                f"{self.name} returned {len(vectors)} embeddings for {len(texts)} inputs"
            )

        return [_fit_dimensions(_normalise(vector), self.dimensions) for vector in vectors]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        batch_size = max(1, settings.EMBEDDING_BATCH_SIZE)
        for start in range(0, len(texts), batch_size):
            results.extend(await self._post(texts[start : start + batch_size], "document"))
        return results

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._post([text], "query")
        return vectors[0]


class VoyageEmbedder(HTTPEmbedder):
    name = "voyage"
    url = VOYAGE_URL
    supports_input_type = True


class OpenAIEmbedder(HTTPEmbedder):
    name = "openai"
    url = OPENAI_URL
    supports_input_type = False


_PROVIDERS: dict[str, type[BaseEmbedder]] = {
    "hash": HashEmbedder,
    "voyage": VoyageEmbedder,
    "openai": OpenAIEmbedder,
}


def get_embedder(provider: str | None = None) -> BaseEmbedder:
    """Build the configured embedder. Providers are cheap to construct."""
    key = (provider or settings.EMBEDDING_PROVIDER).lower()
    embedder_class = _PROVIDERS.get(key)
    if embedder_class is None:
        raise EmbeddingError(f"Unknown embedding provider: {key}")
    return embedder_class()
