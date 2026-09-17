"""The indexing pipeline: extract -> chunk -> embed -> store.

Ingestion runs as a background task after upload, so the upload request returns
as soon as the file is safely on disk. Progress is reported through the
document's ``status`` field, which the client can poll.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import session_scope
from src.models.document import DocumentStatus
from src.services.chunking import chunk_pages
from src.services.chunks import ChunkService
from src.services.documents import DocumentService
from src.services.embeddings import BaseEmbedder, get_embedder
from src.services.extraction import extract_pages
from src.utils.errors import DocMindError

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    document_id: uuid.UUID
    status: str
    page_count: int
    chunk_count: int
    error: str | None = None


class IngestionService:
    def __init__(
        self,
        embedder: BaseEmbedder | None = None,
        documents: DocumentService | None = None,
        chunks: ChunkService | None = None,
    ) -> None:
        self._embedder = embedder
        self.documents = documents or DocumentService()
        self.chunks = chunks or ChunkService()

    @property
    def embedder(self) -> BaseEmbedder:
        if self._embedder is None:
            self._embedder = get_embedder()
        return self._embedder

    async def ingest(self, document_id: uuid.UUID, session: AsyncSession) -> IngestionResult:
        """Index one document. Never raises: failures land in the document row."""
        document = await self.documents.get_document_by_id(document_id, session)
        if document is None:
            logger.warning("Ingestion skipped: document %s no longer exists", document_id)
            return IngestionResult(document_id, DocumentStatus.FAILED, 0, 0, "Document not found")

        await self.documents.update_status(document_id, session, DocumentStatus.PROCESSING)

        try:
            pages = extract_pages(document.file_path)
            if not pages:
                raise DocMindError(
                    "No readable text found in the document. "
                    "Scanned files need OCR before they can be indexed."
                )

            text_chunks = chunk_pages(pages)
            if not text_chunks:
                raise DocMindError("The document produced no text chunks")

            embeddings = await self.embedder.embed_documents(
                [chunk.content for chunk in text_chunks]
            )
            chunk_count = await self.chunks.replace_chunks(
                document_id, text_chunks, embeddings, session
            )

            await self.documents.update_status(
                document_id,
                session,
                DocumentStatus.READY,
                page_count=len(pages),
                chunk_count=chunk_count,
            )
            logger.info(
                "Indexed document %s: %d pages, %d chunks", document_id, len(pages), chunk_count
            )
            return IngestionResult(document_id, DocumentStatus.READY, len(pages), chunk_count)

        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            logger.exception("Ingestion failed for document %s", document_id)
            await session.rollback()
            await self.documents.update_status(
                document_id, session, DocumentStatus.FAILED, error_message=message
            )
            return IngestionResult(document_id, DocumentStatus.FAILED, 0, 0, message)


async def ingest_document(document_id: uuid.UUID) -> IngestionResult:
    """Entry point for BackgroundTasks - owns its own database session."""
    async with session_scope() as session:
        return await IngestionService().ingest(document_id, session)
