from sqlalchemy.ext.asyncio import AsyncSession
from src.models.document import Document
from sqlalchemy import select
from fastapi import HTTPException
import uuid

class DocumentService:

    async def create_document(
        self,
        user_id: uuid.UUID,
        filename: str,
        file_path: str,
        file_type: str,
        file_size: int,
        session: AsyncSession
    ):
        new_document = Document(
            user_id=user_id,
            filename=filename,
            file_path=file_path,
            file_type=file_type,
            file_size=file_size,
        )
        session.add(new_document)

        await session.commit()
        await session.refresh(new_document)

        return new_document
    async def get_document_by_id(
                self,
                document_id: uuid.UUID,
                session: AsyncSession
):
        statement = select(Document).where(
        Document.id == document_id
    )

        result = await session.execute(statement)

        return result.scalar_one_or_none()

    
    async def get_user_documents(
            self,
            user_id: uuid.UUID,
            session: AsyncSession
):
        statement = select(Document).where(
        Document.user_id == user_id).order_by(Document.created_at.desc())

        result = await session.execute(statement)

        return result.scalars().all()

    
    async def delete_document(
            self,
            document_id: uuid.UUID,
            user_id: uuid.UUID,
            session: AsyncSession
):  
        statement = select(Document).where(Document.id == document_id,Document.user_id == user_id)

        result = await session.execute(statement)
        document = result.scalar_one_or_none()

        if document is None:
            raise HTTPException(
                status_code=404,
                detail="Document not found"
        )

        await session.delete(document)
        await session.commit()

        return document