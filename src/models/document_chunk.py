from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config import settings
from src.db.database import Base
from src.models.mixins import utcnow

if TYPE_CHECKING:
    from src.models.document import Document

# pgvector is a PostgreSQL extension. The JSON variant keeps the model usable on
# SQLite (used by the test suite); similarity search falls back to an in-Python
# cosine computation on that dialect - see src/services/chunks.py.
EmbeddingType = Vector(settings.EMBEDDING_DIMENSIONS).with_variant(JSON(), "sqlite")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_doc_index"),
        # Approximate nearest-neighbour index for cosine similarity. The
        # postgresql_* options are ignored on other dialects.
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_estimate: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingType, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")
