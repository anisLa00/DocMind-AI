import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.conversation import Conversation
from src.models.document import Document, DocumentStatus
from src.schemas.conversations import CreateConversationModel
from src.services.documents import DocumentService
from src.utils.errors import DocumentNotReadyError, NotFoundError

_TITLE_MAX = 255


class ConversationService:
    def __init__(self, documents: DocumentService | None = None) -> None:
        self.documents = documents or DocumentService()

    async def create_conversation(
        self, user_id: uuid.UUID, data: CreateConversationModel, session: AsyncSession
    ) -> Conversation:
        document = await self.documents.get_owned_document(data.document_id, user_id, session)

        if document.status != DocumentStatus.READY:
            raise DocumentNotReadyError(
                f"Document is not ready for questions (status: {document.status})"
            )

        title = (data.title or f"Chat about {document.filename}").strip()[:_TITLE_MAX]

        conversation = Conversation(
            user_id=user_id, document_id=document.id, title=title or document.filename
        )
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)
        return conversation

    async def get_owned_conversation(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        session: AsyncSession,
        with_messages: bool = False,
    ) -> Conversation:
        statement = select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
        if with_messages:
            statement = statement.options(selectinload(Conversation.messages))

        result = await session.execute(statement)
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise NotFoundError("Conversation not found")
        return conversation

    async def get_user_conversations(
        self,
        user_id: uuid.UUID,
        session: AsyncSession,
        document_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Conversation]:
        statement = select(Conversation).where(Conversation.user_id == user_id)
        if document_id is not None:
            statement = statement.where(Conversation.document_id == document_id)

        statement = statement.order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)
        result = await session.execute(statement)
        return result.scalars().all()

    async def rename_conversation(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str,
        session: AsyncSession,
    ) -> Conversation:
        conversation = await self.get_owned_conversation(conversation_id, user_id, session)
        conversation.title = title.strip()[:_TITLE_MAX]
        await session.commit()
        await session.refresh(conversation)
        return conversation

    async def delete_conversation(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
    ) -> Conversation:
        conversation = await self.get_owned_conversation(conversation_id, user_id, session)
        await session.delete(conversation)
        await session.commit()
        return conversation

    async def get_document_for_conversation(
        self, conversation: Conversation, session: AsyncSession
    ) -> Document:
        document = await self.documents.get_document_by_id(conversation.document_id, session)
        if document is None:
            raise NotFoundError("The document backing this conversation no longer exists")
        return document
