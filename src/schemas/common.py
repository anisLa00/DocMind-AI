from pydantic import BaseModel


class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    blocklist: str
    llm_configured: bool
    embedding_provider: str
