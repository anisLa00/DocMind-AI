import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.models.user import User
from src.schemas.messages import MessageModel
from src.services.conversations import ConversationService
from src.services.messages import MessageService
from src.utils.dependencies import get_current_user

message_router = APIRouter(prefix="/messages", tags=["Messages"])


@message_router.get("/conversation/{conversation_id}", response_model=list[MessageModel])
async def list_messages(
    conversation_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await ConversationService().get_owned_conversation(conversation_id, current_user.id, session)
    return await MessageService().get_conversation_messages(
        conversation_id, session, limit=limit, offset=offset
    )
