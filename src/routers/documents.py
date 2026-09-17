import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.models.document import DocumentStatus
from src.models.user import User
from src.schemas.chunks import ChunkModel
from src.schemas.common import MessageResponse
from src.schemas.documents import DocumentModel
from src.services.chunks import ChunkService
from src.services.documents import DocumentService
from src.services.ingestion import ingest_document
from src.services.storage import StorageService
from src.utils.dependencies import get_current_user

document_router = APIRouter(prefix="/documents", tags=["Documents"])


@document_router.post("/upload", response_model=DocumentModel, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Store a document and queue it for indexing.

    Returns as soon as the file is on disk; poll the document's ``status`` (or
    `GET /documents/{id}/status`) to see when it becomes `ready`.
    """
    storage = StorageService()
    document_id = uuid.uuid4()

    file_path, file_size = await storage.save_upload(file, current_user.id, document_id)

    try:
        document = await DocumentService(storage).create_document(
            user_id=current_user.id,
            filename=file.filename or file_path.name,
            file_path=str(file_path),
            file_type=file.content_type or "application/octet-stream",
            file_size=file_size,
            session=session,
            document_id=document_id,
        )
    except Exception:
        # Never leave an orphaned file behind if the row could not be written.
        storage.delete(file_path)
        raise

    background_tasks.add_task(ingest_document, document.id)
    return document


@document_router.get("/", response_model=list[DocumentModel])
async def get_my_documents(
    document_status: DocumentStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await DocumentService().get_user_documents(
        user_id=current_user.id,
        session=session,
        status=document_status.value if document_status else None,
        limit=limit,
        offset=offset,
    )


@document_router.get("/{document_id}", response_model=DocumentModel)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await DocumentService().get_owned_document(document_id, current_user.id, session)


@document_router.get("/{document_id}/status", response_model=DocumentModel)
async def get_document_status(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Lightweight endpoint for polling ingestion progress."""
    return await DocumentService().get_owned_document(document_id, current_user.id, session)


@document_router.get("/{document_id}/chunks", response_model=list[ChunkModel])
async def get_document_chunks(
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


@document_router.post(
    "/{document_id}/reindex",
    response_model=DocumentModel,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reindex_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Re-run the pipeline, e.g. after changing the chunk size or embedder."""
    service = DocumentService()
    document = await service.get_owned_document(document_id, current_user.id, session)

    document = (
        await service.update_status(
            document_id, session, DocumentStatus.PENDING, chunk_count=0, page_count=0
        )
        or document
    )

    background_tasks.add_task(ingest_document, document_id)
    return document


@document_router.delete("/{document_id}", response_model=MessageResponse)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await DocumentService().delete_document(document_id, current_user.id, session)
    return {"message": "Document deleted successfully"}
