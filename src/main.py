"""DocMind AI - an AI-powered document assistant built on retrieval-augmented generation."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src import __version__
from src.config import settings
from src.db.database import dispose_engine
from src.routers.auth import auth_router
from src.routers.conversations import conversation_router
from src.routers.document_chunks import chunk_router
from src.routers.documents import document_router
from src.routers.health import health_router
from src.routers.messages import message_router
from src.routers.users import user_router
from src.utils.errors import (
    ConflictError,
    DocMindError,
    DocumentNotReadyError,
    EmbeddingError,
    FileTooLargeError,
    LLMError,
    NotFoundError,
    UnsupportedFileTypeError,
    ValidationError,
)
from src.utils.redis import close_blocklist

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DESCRIPTION = """
Upload a document, let DocMind index it, then ask questions and get answers
grounded in the document with citations back to the source passages.

**Typical flow**

1. `POST /users/` - sign up, then `POST /auth/login` for a token.
2. `POST /documents/upload` - upload a PDF, DOCX, TXT or Markdown file.
3. Poll `GET /documents/{id}/status` until the status is `ready`.
4. `POST /conversations/` - start a conversation about that document.
5. `POST /conversations/{id}/chat` - ask questions (or `/chat/stream` for SSE).
"""

# Domain error -> HTTP status. Ordered most specific first: the handler walks
# this mapping and the first matching class wins.
_ERROR_STATUS: tuple[tuple[type[DocMindError], int], ...] = (
    (UnsupportedFileTypeError, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE),
    (FileTooLargeError, status.HTTP_413_CONTENT_TOO_LARGE),
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (DocumentNotReadyError, status.HTTP_409_CONFLICT),
    (ValidationError, status.HTTP_400_BAD_REQUEST),
    (EmbeddingError, status.HTTP_502_BAD_GATEWAY),
    (LLMError, status.HTTP_502_BAD_GATEWAY),
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    logger.info(
        "%s %s starting (env=%s, embeddings=%s, llm=%s)",
        settings.APP_NAME,
        __version__,
        settings.ENVIRONMENT,
        settings.EMBEDDING_PROVIDER,
        settings.LLM_MODEL,
    )
    try:
        yield
    finally:
        await close_blocklist()
        await dispose_engine()


app = FastAPI(
    title="DocMind AI",
    description=DESCRIPTION,
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _status_for(exc: DocMindError) -> int | None:
    for error_class, status_code in _ERROR_STATUS:
        if isinstance(exc, error_class):
            return status_code
    return None


@app.exception_handler(DocMindError)
async def docmind_error_handler(request: Request, exc: DocMindError) -> JSONResponse:
    status_code = _status_for(exc)
    if status_code is None:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.exception("Unhandled domain error on %s", request.url.path, exc_info=exc)

    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


@app.get("/", tags=["Health"])
def root() -> dict[str, str]:
    return {
        "message": "DocMind AI API is running",
        "version": __version__,
        "docs": "/docs",
    }


app.include_router(health_router)
app.include_router(user_router)
app.include_router(auth_router)
app.include_router(document_router)
app.include_router(chunk_router)
app.include_router(conversation_router)
app.include_router(message_router)
