import uuid

from pydantic import BaseModel, Field

from src.schemas.chunks import ChunkSearchResult
from src.schemas.messages import MessageModel


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    answer: str
    sources: list[ChunkSearchResult] = []
    message: MessageModel
    model: str
