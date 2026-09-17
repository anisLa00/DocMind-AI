"""Retrieval-augmented generation: retrieve passages, then answer from them."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.conversation import Conversation
from src.models.document import Document
from src.models.message import Message, MessageRole
from src.schemas.chunks import ChunkSearchResult
from src.services.chunks import ChunkService
from src.services.embeddings import BaseEmbedder
from src.services.llm import EXTRACTIVE_MODEL, LLMService
from src.services.messages import MessageService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are DocMind AI, an assistant that answers questions about \
a single document the user has uploaded.

Ground every answer in the excerpts provided with the question:
- Use only what the excerpts say. Do not rely on outside knowledge, and do not \
guess at what the rest of the document might contain.
- Cite the excerpts you used with their bracketed markers, like [1] or [2][3], \
placed right after the claim they support.
- If the excerpts do not contain the answer, say so plainly and suggest what the \
user could ask instead. Never invent a citation.
- Quote short phrases verbatim when the exact wording matters.
- Answer in the language the user writes in, and keep it concise.

Document: {filename}"""

_NO_CONTEXT_MESSAGE = (
    "I could not find anything in this document that relates to your question. "
    "Try rephrasing it, or ask about a topic the document actually covers."
)

# Assistant turns are replayed to the model without their source list, so the
# citation markers stay meaningful without re-sending every earlier excerpt.
_HISTORY_TURNS = 10


@dataclass
class RAGAnswer:
    answer: str
    sources: list[ChunkSearchResult] = field(default_factory=list)
    model: str = EXTRACTIVE_MODEL
    message: Message | None = None


class RAGService:
    def __init__(
        self,
        chunks: ChunkService | None = None,
        messages: MessageService | None = None,
        llm: LLMService | None = None,
        embedder: BaseEmbedder | None = None,
    ) -> None:
        self.chunks = chunks or ChunkService()
        self.messages = messages or MessageService()
        self.llm = llm or LLMService()
        self.embedder = embedder

    # ---- prompt building ------------------------------------------------------

    def build_context(self, results: list[ChunkSearchResult]) -> str:
        """Render retrieved passages as numbered, citable excerpts."""
        blocks: list[str] = []
        budget = settings.RAG_MAX_CONTEXT_CHARS

        for position, result in enumerate(results, start=1):
            location = f", page {result.page_number}" if result.page_number else ""
            header = f"[{position}] (from {result.document_filename or 'document'}{location})"
            block = f"{header}\n{result.content}"

            if len(block) > budget:
                break
            budget -= len(block)
            blocks.append(block)

        return "\n\n".join(blocks)

    def build_system_prompt(self, document: Document) -> str:
        return SYSTEM_PROMPT.format(filename=document.filename)

    def build_user_turn(self, question: str, context: str) -> str:
        if not context:
            return f"No excerpts from the document matched this question.\n\nQuestion: {question}"
        return (
            "Here are the excerpts from the document that best match the question.\n\n"
            f"<excerpts>\n{context}\n</excerpts>\n\n"
            f"Question: {question}"
        )

    def _extractive_answer(self, results: list[ChunkSearchResult]) -> str:
        """Used when no API key is configured: quote the best passages verbatim."""
        if not results:
            return _NO_CONTEXT_MESSAGE

        lines = [
            "Answer generation is not configured (no ANTHROPIC_API_KEY), so here "
            "are the passages from the document that best match your question:",
            "",
        ]
        for position, result in enumerate(results, start=1):
            location = f" (page {result.page_number})" if result.page_number else ""
            excerpt = result.content.strip()
            if len(excerpt) > 600:
                excerpt = f"{excerpt[:600].rstrip()}..."
            lines.append(f"[{position}]{location} {excerpt}")
            lines.append("")

        return "\n".join(lines).strip()

    # ---- retrieval ------------------------------------------------------------

    async def retrieve(
        self,
        question: str,
        conversation: Conversation,
        session: AsyncSession,
        top_k: int | None = None,
    ) -> list[ChunkSearchResult]:
        return await self.chunks.search(
            query=question,
            user_id=conversation.user_id,
            session=session,
            document_id=conversation.document_id,
            top_k=top_k or settings.RAG_TOP_K,
            embedder=self.embedder,
        )

    @staticmethod
    def _sources_payload(results: list[ChunkSearchResult]) -> list[dict[str, object]]:
        return [
            {
                "marker": position,
                "chunk_id": str(result.id),
                "document_id": str(result.document_id),
                "filename": result.document_filename,
                "page_number": result.page_number,
                "chunk_index": result.chunk_index,
                "score": result.score,
            }
            for position, result in enumerate(results, start=1)
        ]

    async def _build_prompt(
        self,
        question: str,
        conversation: Conversation,
        document: Document,
        session: AsyncSession,
        results: list[ChunkSearchResult],
    ) -> tuple[str, list[dict[str, str]]]:
        history = await self.messages.get_history(conversation.id, session, limit=_HISTORY_TURNS)
        context = self.build_context(results)
        turns = [*history, {"role": "user", "content": self.build_user_turn(question, context)}]
        return self.build_system_prompt(document), turns

    # ---- answering ------------------------------------------------------------

    async def answer(
        self,
        question: str,
        conversation: Conversation,
        document: Document,
        session: AsyncSession,
        top_k: int | None = None,
    ) -> RAGAnswer:
        results = await self.retrieve(question, conversation, session, top_k)
        system, turns = await self._build_prompt(question, conversation, document, session, results)

        # Persist the question before calling out, so a failed generation still
        # leaves the conversation in a consistent, replayable state.
        await self.messages.add_message(conversation.id, MessageRole.USER, question, session)

        if self.llm.available:
            llm_answer = await self.llm.generate(system, turns)
            answer_text, model = llm_answer.text, llm_answer.model
        else:
            answer_text, model = self._extractive_answer(results), EXTRACTIVE_MODEL

        stored = await self.messages.add_message(
            conversation.id,
            MessageRole.ASSISTANT,
            answer_text,
            session,
            sources=self._sources_payload(results),
        )

        return RAGAnswer(answer=answer_text, sources=results, model=model, message=stored)

    async def stream_answer(
        self,
        question: str,
        conversation: Conversation,
        document: Document,
        session: AsyncSession,
        top_k: int | None = None,
    ) -> AsyncIterator[tuple[str, object]]:
        """Yield ``(event, payload)`` pairs: ``sources``, then ``delta``s, then ``done``."""
        results = await self.retrieve(question, conversation, session, top_k)
        system, turns = await self._build_prompt(question, conversation, document, session, results)

        await self.messages.add_message(conversation.id, MessageRole.USER, question, session)
        yield "sources", [result.model_dump(mode="json") for result in results]

        collected: list[str] = []
        if self.llm.available:
            async for delta in self.llm.stream(system, turns):
                collected.append(delta)
                yield "delta", delta
        else:
            text = self._extractive_answer(results)
            collected.append(text)
            yield "delta", text

        answer_text = "".join(collected).strip() or _NO_CONTEXT_MESSAGE
        stored = await self.messages.add_message(
            conversation.id,
            MessageRole.ASSISTANT,
            answer_text,
            session,
            sources=self._sources_payload(results),
        )

        yield "done", {"message_id": str(stored.id), "conversation_id": str(conversation.id)}
