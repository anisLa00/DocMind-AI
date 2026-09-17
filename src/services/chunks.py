"""Persistence and similarity search for document chunks."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.document import Document
from src.models.document_chunk import DocumentChunk
from src.schemas.chunks import ChunkSearchResult
from src.services.chunking import TextChunk
from src.services.embeddings import BaseEmbedder, cosine_similarity, get_embedder

# How many rows the in-Python fallback will score. pgvector does this in the
# database; on SQLite we cap the work so a large corpus cannot blow up memory.
_PYTHON_SCAN_LIMIT = 2000


class ChunkService:
    async def replace_chunks(
        self,
        document_id: uuid.UUID,
        chunks: Sequence[TextChunk],
        embeddings: Sequence[Sequence[float]],
        session: AsyncSession,
    ) -> int:
        """Swap in a fresh set of chunks for a document (idempotent re-indexing)."""
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must be the same length")

        await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))

        session.add_all(
            [
                DocumentChunk(
                    document_id=document_id,
                    content=chunk.content,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    token_estimate=chunk.token_estimate,
                    embedding=list(embedding),
                )
                for chunk, embedding in zip(chunks, embeddings, strict=False)
            ]
        )

        await session.commit()
        return len(chunks)

    async def get_document_chunks(
        self,
        document_id: uuid.UUID,
        session: AsyncSession,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[DocumentChunk]:
        statement = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(statement)
        return result.scalars().all()

    async def count_document_chunks(self, document_id: uuid.UUID, session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
        )
        return int(result.scalar_one())

    async def delete_document_chunks(self, document_id: uuid.UUID, session: AsyncSession) -> None:
        await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        await session.commit()

    async def search(
        self,
        query: str,
        user_id: uuid.UUID,
        session: AsyncSession,
        document_id: uuid.UUID | None = None,
        top_k: int | None = None,
        embedder: BaseEmbedder | None = None,
    ) -> list[ChunkSearchResult]:
        """Rank a user's chunks by cosine similarity to ``query``."""
        top_k = top_k or settings.RAG_TOP_K
        embedder = embedder or get_embedder()
        query_vector = await embedder.embed_query(query)

        if session.bind is not None and session.bind.dialect.name == "postgresql":
            return await self._search_pgvector(query_vector, user_id, session, document_id, top_k)
        return await self._search_python(query_vector, user_id, session, document_id, top_k)

    def _base_statement(self, user_id: uuid.UUID, document_id: uuid.UUID | None):
        statement = (
            select(DocumentChunk, Document.filename)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.user_id == user_id, DocumentChunk.embedding.is_not(None))
        )
        if document_id is not None:
            statement = statement.where(DocumentChunk.document_id == document_id)
        return statement

    async def _search_pgvector(
        self,
        query_vector: list[float],
        user_id: uuid.UUID,
        session: AsyncSession,
        document_id: uuid.UUID | None,
        top_k: int,
    ) -> list[ChunkSearchResult]:
        # `<=>` is cosine distance in pgvector: similarity = 1 - distance.
        distance = DocumentChunk.embedding.cosine_distance(query_vector)
        statement = (
            self._base_statement(user_id, document_id)
            .add_columns(distance.label("distance"))
            .order_by(distance)
            .limit(top_k)
        )

        result = await session.execute(statement)
        return [
            self._to_result(chunk, filename, 1.0 - float(dist))
            for chunk, filename, dist in result.all()
        ]

    async def _search_python(
        self,
        query_vector: list[float],
        user_id: uuid.UUID,
        session: AsyncSession,
        document_id: uuid.UUID | None,
        top_k: int,
    ) -> list[ChunkSearchResult]:
        """Fallback for dialects without pgvector (the SQLite test database)."""
        statement = self._base_statement(user_id, document_id).limit(_PYTHON_SCAN_LIMIT)
        result = await session.execute(statement)

        scored = [
            (cosine_similarity(query_vector, list(chunk.embedding or [])), chunk, filename)
            for chunk, filename in result.all()
        ]
        scored.sort(key=lambda row: row[0], reverse=True)

        return [
            self._to_result(chunk, filename, score) for score, chunk, filename in scored[:top_k]
        ]

    @staticmethod
    def _to_result(chunk: DocumentChunk, filename: str | None, score: float) -> ChunkSearchResult:
        return ChunkSearchResult(
            id=chunk.id,
            document_id=chunk.document_id,
            document_filename=filename,
            content=chunk.content,
            chunk_index=chunk.chunk_index,
            page_number=chunk.page_number,
            score=round(score, 6),
        )
