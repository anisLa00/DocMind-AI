"""Unit tests for prompt construction and the no-API-key fallback."""

import uuid

import pytest

from src.config import settings
from src.schemas.chunks import ChunkSearchResult
from src.services.rag import RAGService


def make_result(content: str, page: int | None = 1, score: float = 0.5) -> ChunkSearchResult:
    return ChunkSearchResult(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_filename="report.pdf",
        content=content,
        chunk_index=0,
        page_number=page,
        score=score,
    )


@pytest.fixture
def service() -> RAGService:
    return RAGService()


def test_context_numbers_each_excerpt(service):
    context = service.build_context([make_result("First."), make_result("Second.")])

    assert "[1]" in context
    assert "[2]" in context
    assert context.index("[1]") < context.index("[2]")


def test_context_includes_the_page_reference(service):
    context = service.build_context([make_result("Revenue grew.", page=7)])

    assert "page 7" in context
    assert "report.pdf" in context


def test_context_omits_the_page_when_unknown(service):
    context = service.build_context([make_result("Revenue grew.", page=None)])

    assert "page" not in context


def test_context_respects_the_character_budget(service, monkeypatch):
    monkeypatch.setattr(settings, "RAG_MAX_CONTEXT_CHARS", 120)

    context = service.build_context([make_result("x" * 80), make_result("y" * 80)])

    assert "x" * 80 in context
    assert "y" * 80 not in context


def test_empty_results_give_an_empty_context(service):
    assert service.build_context([]) == ""


def test_the_user_turn_carries_the_question_and_excerpts(service):
    turn = service.build_user_turn("What changed?", "[1] Revenue grew.")

    assert "<excerpts>" in turn
    assert "[1] Revenue grew." in turn
    assert "Question: What changed?" in turn


def test_the_user_turn_says_so_when_nothing_matched(service):
    turn = service.build_user_turn("What changed?", "")

    assert "No excerpts" in turn
    assert "Question: What changed?" in turn


def test_the_system_prompt_names_the_document(service):
    class FakeDocument:
        filename = "annual-report.pdf"

    prompt = service.build_system_prompt(FakeDocument())

    assert "annual-report.pdf" in prompt
    assert "Cite the excerpts" in prompt
    assert "do not guess" in prompt.lower()


def test_the_fallback_quotes_the_best_passages(service):
    answer = service._extractive_answer([make_result("Revenue grew twelve percent.", page=3)])

    assert "ANTHROPIC_API_KEY" in answer
    assert "Revenue grew twelve percent." in answer
    assert "page 3" in answer


def test_the_fallback_truncates_long_passages(service):
    answer = service._extractive_answer([make_result("z" * 2000)])

    assert "..." in answer
    assert len(answer) < 1200


def test_the_fallback_says_so_when_nothing_matched(service):
    answer = service._extractive_answer([])

    assert "could not find anything" in answer


def test_source_payloads_are_json_serialisable(service):
    payload = service._sources_payload([make_result("Revenue grew.", page=2)])

    assert payload[0]["marker"] == 1
    assert payload[0]["page_number"] == 2
    assert isinstance(payload[0]["chunk_id"], str)
    assert isinstance(payload[0]["document_id"], str)
