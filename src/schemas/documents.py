import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentModel(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    file_path: str
    file_type: str
    file_size: int
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)