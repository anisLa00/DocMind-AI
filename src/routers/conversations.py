import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.models.user import User
from src.schemas.chat import ChatRequest, ChatResponse
from src.schemas.common import MessageResponse
from src.schemas.conversations import (
    ConversationDetailModel,
    ConversationModel,
    CreateConversationModel,
    UpdateConversationModel,
)
from src.schemas.messages import MessageModel
from src.services.conversations import ConversationService
from src.services.messages import MessageService
from src.services.rag import RAGService
from src.utils.dependencies import get_current_user
from src.utils.errors import LLMError

conversation_router = APIRouter(prefix="/conversations", tags=["Conversations"])


@conversation_router.post(
    "/", response_model=ConversationModel, status_code=status.HTTP_201_CREATED
)
async def create_conversation(
    data: CreateConversationModel,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Start a conversation about one indexed document."""
    return await ConversationService().create_conversation(current_user.id, data, session)


@conversation_router.get("/", response_model=list[ConversationModel])
async def list_conversations(
    document_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await ConversationService().get_user_conversations(
        current_user.id, session, document_id=document_id, limit=limit, offset=offset
    )


@conversation_router.get("/{conversation_id}", response_model=ConversationDetailModel)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await ConversationService().get_owned_conversation(
        conversation_id, current_user.id, session, with_messages=True
    )


@conversation_router.get("/{conversation_id}/messages", response_model=list[MessageModel])
async def list_conversation_messages(
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


@conversation_router.patch("/{conversation_id}", response_model=ConversationModel)
async def rename_conversation(
    conversation_id: uuid.UUID,
    data: UpdateConversationModel,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await ConversationService().rename_conversation(
        conversation_id, current_user.id, data.title, session
    )


@conversation_router.delete("/{conversation_id}", response_model=MessageResponse)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await ConversationService().delete_conversation(conversation_id, current_user.id, session)
    return {"message": "Conversation deleted successfully"}


@conversation_router.post("/{conversation_id}/chat", response_model=ChatResponse)
async def chat(
    conversation_id: uuid.UUID,
    data: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Ask a question. The answer is grounded in the conversation's document."""
    service = ConversationService()
    conversation = await service.get_owned_conversation(conversation_id, current_user.id, session)
    document = await service.get_document_for_conversation(conversation, session)

    result = await RAGService().answer(
        question=data.question,
        conversation=conversation,
        document=document,
        session=session,
        top_k=data.top_k,
    )

    return ChatResponse(
        conversation_id=conversation.id,
        answer=result.answer,
        sources=result.sources,
        message=MessageModel.model_validate(result.message),
        model=result.model,
    )


@conversation_router.post("/{conversation_id}/chat/stream")
async def chat_stream(
    conversation_id: uuid.UUID,
    data: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Same as `/chat`, streamed as server-sent events."""
    service = ConversationService()
    conversation = await service.get_owned_conversation(conversation_id, current_user.id, session)
    document = await service.get_document_for_conversation(conversation, session)

    async def event_stream() -> AsyncIterator[str]:
        try:
            generator = RAGService().stream_answer(
                question=data.question,
                conversation=conversation,
                document=document,
                session=session,
                top_k=data.top_k,
            )
            async for event, payload in generator:
                yield f"event: {event}\ndata: {json.dumps(payload)}\n\n"
        except LLMError as exc:
            # The response has already begun, so the error has to travel as an
            # event rather than as an HTTP status code.
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
