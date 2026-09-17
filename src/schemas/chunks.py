import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChunkModel(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    content: str
    chunk_index: int
    page_number: int | None = None
    token_estimate: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChunkSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    document_id: uuid.UUID | None = None
    top_k: int = Field(default=5, ge=1, le=50)


class ChunkSearchResult(BaseModel):
    """A retrieved chunk plus its similarity to the query (1.0 = identical)."""

    id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str | None = None
    content: str
    chunk_index: int
    page_number: int | None = None
    score: float
