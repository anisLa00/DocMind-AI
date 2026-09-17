import pytest

from src.services.embeddings import (
    HashEmbedder,
    cosine_similarity,
    get_embedder,
)
from src.utils.errors import EmbeddingError


async def test_embeddings_have_the_configured_width():
    embedder = HashEmbedder(dimensions=256)
    [vector] = await embedder.embed_documents(["hello world"])

    assert len(vector) == 256


async def test_embeddings_are_unit_length():
    embedder = HashEmbedder()
    [vector] = await embedder.embed_documents(["hello world"])

    assert sum(value * value for value in vector) == pytest.approx(1.0, abs=1e-9)


async def test_embeddings_are_deterministic():
    embedder = HashEmbedder()
    first = await embedder.embed_documents(["repeatable text"])
    second = await embedder.embed_documents(["repeatable text"])

    assert first == second


async def test_related_text_scores_above_unrelated_text():
    embedder = HashEmbedder()
    related, rephrased, unrelated = await embedder.embed_documents(
        [
            "European revenue grew twelve percent this quarter.",
            "Revenue in Europe grew by twelve percent in the quarter.",
            "Penguins huddle together through the antarctic winter.",
        ]
    )

    assert cosine_similarity(related, rephrased) > cosine_similarity(related, unrelated)


async def test_empty_text_yields_a_zero_vector():
    embedder = HashEmbedder(dimensions=32)
    [vector] = await embedder.embed_documents([""])

    assert vector == [0.0] * 32


def test_cosine_similarity_handles_zero_vectors():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
    assert cosine_similarity([], []) == 0.0


def test_cosine_similarity_of_identical_vectors_is_one():
    vector = [0.6, 0.8]
    assert cosine_similarity(vector, vector) == pytest.approx(1.0)


def test_get_embedder_returns_the_configured_provider():
    assert isinstance(get_embedder(), HashEmbedder)


def test_unknown_provider_is_rejected():
    with pytest.raises(EmbeddingError):
        get_embedder("does-not-exist")


def test_http_providers_require_an_api_key():
    with pytest.raises(EmbeddingError, match="EMBEDDING_API_KEY"):
        get_embedder("voyage")
