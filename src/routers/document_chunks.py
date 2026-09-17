import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.models.user import User
from src.schemas.chunks import ChunkModel, ChunkSearchRequest, ChunkSearchResult
from src.services.chunks import ChunkService
from src.services.documents import DocumentService
from src.utils.dependencies import get_current_user

chunk_router = APIRouter(prefix="/chunks", tags=["Chunks"])


@chunk_router.post("/search", response_model=list[ChunkSearchResult])
async def search_chunks(
    data: ChunkSearchRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Semantic search across the caller's documents (or one of them)."""
    if data.document_id is not None:
        await DocumentService().get_owned_document(data.document_id, current_user.id, session)

    return await ChunkService().search(
        query=data.query,
        user_id=current_user.id,
        session=session,
        document_id=data.document_id,
        top_k=data.top_k,
    )


@chunk_router.get("/document/{document_id}", response_model=list[ChunkModel])
async def list_document_chunks(
    document_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await DocumentService().get_owned_document(document_id, current_user.id, session)
    return await ChunkService().get_document_chunks(
        document_id, session, limit=limit, offset=offset
    )
