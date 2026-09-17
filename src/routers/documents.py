from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from fastapi import HTTPException

from src.db.database import get_session
from src.models.user import User
from src.utils.dependencies import get_current_user
from src.services.documents import DocumentService
from src.schemas.documents import DocumentModel
import os

document_router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)
@document_router.post("/upload",response_model=DocumentModel)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    filename = file.filename
    file_type = file.content_type
    content = await file.read()
    file_size = len(content)

    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, filename)

    with open(file_path, "wb") as buffer:
        buffer.write(content)

    document = await DocumentService().create_document(
    user_id=current_user.id,
    filename=filename,
    file_path=file_path,
    file_type=file_type,
    file_size=file_size,
    session=session
)

    return document 
@document_router.get("/",response_model=list[DocumentModel])
async def get_my_documents(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
    ):
    return await DocumentService().get_user_documents(
        user_id=current_user.id,
        session=session
    ) 
@document_router.get(
    "/{document_id}",
    response_model=DocumentModel
)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    document = await DocumentService().get_document_by_id(
        document_id=document_id,
        session=session
    )

    if document is None or document.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    return document

@document_router.delete("/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    await DocumentService().delete_document(
        document_id=document_id,
        user_id=current_user.id,
        session=session
    )

    return {
        "message": "Document deleted successfully"
    }  