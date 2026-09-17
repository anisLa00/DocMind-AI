import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.conversation import Conversation
from src.models.message import Message, MessageRole
from src.models.mixins import utcnow


class MessageService:
    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        session: AsyncSession,
        sources: list[dict[str, Any]] | None = None,
        commit: bool = True,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id, role=role, content=content, sources=sources
        )
        session.add(message)

        if commit:
            # Touch the conversation so the list view sorts by real activity.
            conversation = await session.get(Conversation, conversation_id)
            if conversation is not None:
                conversation.updated_at = utcnow()
            await session.commit()
            await session.refresh(message)

        return message

    async def get_conversation_messages(
        self,
        conversation_id: uuid.UUID,
        session: AsyncSession,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Message]:
        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(statement)
        return result.scalars().all()

    async def get_history(
        self, conversation_id: uuid.UUID, session: AsyncSession, limit: int = 20
    ) -> list[dict[str, str]]:
        """The most recent turns, oldest-first, shaped for the Messages API."""
        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        result = await session.execute(statement)
        messages = list(result.scalars().all())[::-1]

        return [
            {"role": message.role, "content": message.content}
            for message in messages
            if message.role in (MessageRole.USER, MessageRole.ASSISTANT)
        ]

    async def count_messages(self, conversation_id: uuid.UUID, session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation_id)
        )
        return int(result.scalar_one())
