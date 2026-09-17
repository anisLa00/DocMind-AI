import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.messages import MessageModel


class CreateConversationModel(BaseModel):
    document_id: uuid.UUID
    title: str | None = Field(default=None, max_length=255)


class UpdateConversationModel(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class ConversationModel(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailModel(ConversationModel):
    messages: list[MessageModel] = []
