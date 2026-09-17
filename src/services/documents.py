import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.document import Document, DocumentStatus
from src.services.storage import StorageService
from src.utils.errors import NotFoundError


class DocumentService:
    def __init__(self, storage: StorageService | None = None) -> None:
        self.storage = storage or StorageService()

    async def create_document(
        self,
        user_id: uuid.UUID,
        filename: str,
        file_path: str,
        file_type: str,
        file_size: int,
        session: AsyncSession,
        document_id: uuid.UUID | None = None,
        status: str = DocumentStatus.PENDING,
    ) -> Document:
        new_document = Document(
            user_id=user_id,
            filename=filename,
            file_path=file_path,
            file_type=file_type,
            file_size=file_size,
            status=status,
        )
        if document_id is not None:
            new_document.id = document_id

        session.add(new_document)
        await session.commit()
        await session.refresh(new_document)
        return new_document

    async def get_document_by_id(
        self, document_id: uuid.UUID, session: AsyncSession
    ) -> Document | None:
        result = await session.execute(select(Document).where(Document.id == document_id))
        return result.scalar_one_or_none()

    async def get_owned_document(
        self, document_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
    ) -> Document:
        """Fetch a document the caller owns.

        A document owned by someone else reports as missing rather than
        forbidden, so this endpoint cannot be used to probe for valid IDs.
        """
        result = await session.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        )
        document = result.scalar_one_or_none()
        if document is None:
            raise NotFoundError("Document not found")
        return document

    async def get_user_documents(
        self,
        user_id: uuid.UUID,
        session: AsyncSession,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Document]:
        statement = select(Document).where(Document.user_id == user_id)
        if status:
            statement = statement.where(Document.status == status)

        statement = statement.order_by(Document.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(statement)
        return result.scalars().all()

    async def count_user_documents(self, user_id: uuid.UUID, session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count()).select_from(Document).where(Document.user_id == user_id)
        )
        return int(result.scalar_one())

    async def update_status(
        self,
        document_id: uuid.UUID,
        session: AsyncSession,
        status: str,
        error_message: str | None = None,
        page_count: int | None = None,
        chunk_count: int | None = None,
    ) -> Document | None:
        document = await self.get_document_by_id(document_id, session)
        if document is None:
            return None

        document.status = status
        document.error_message = error_message
        if page_count is not None:
            document.page_count = page_count
        if chunk_count is not None:
            document.chunk_count = chunk_count

        await session.commit()
        await session.refresh(document)
        return document

    async def delete_document(
        self, document_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
    ) -> Document:
        """Delete a document, its chunks (via FK cascade) and its file on disk."""
        document = await self.get_owned_document(document_id, user_id, session)
        file_path = document.file_path

        await session.delete(document)
        await session.commit()

        self.storage.delete(file_path)
        return document
