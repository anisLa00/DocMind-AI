"""RAG pipeline: ingestion status, chunk metadata, cascades and indexes

Revision ID: 8f21c4a7b930
Revises: 5625640ed630
Create Date: 2026-09-17 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8f21c4a7b930"
down_revision: Union[str, Sequence[str], None] = "5625640ed630"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIMESTAMPS = (
    ("users", "created_at"),
    ("users", "updated_at"),
    ("documents", "created_at"),
    ("documents", "updated_at"),
    ("conversations", "created_at"),
    ("conversations", "updated_at"),
    ("document_chunks", "created_at"),
    ("messages", "created_at"),
)

# (constraint name, table, column, referenced table)
FOREIGN_KEYS = (
    ("documents_user_id_fkey", "documents", "user_id", "users"),
    ("conversations_user_id_fkey", "conversations", "user_id", "users"),
    ("conversations_document_id_fkey", "conversations", "document_id", "documents"),
    ("document_chunks_document_id_fkey", "document_chunks", "document_id", "documents"),
    ("messages_conversation_id_fkey", "messages", "conversation_id", "conversations"),
)

INDEXES = (
    ("ix_documents_user_id", "documents", ["user_id"]),
    ("ix_documents_status", "documents", ["status"]),
    ("ix_conversations_user_id", "conversations", ["user_id"]),
    ("ix_conversations_document_id", "conversations", ["document_id"]),
    ("ix_document_chunks_document_id", "document_chunks", ["document_id"]),
    ("ix_messages_conversation_id", "messages", ["conversation_id"]),
)


def upgrade() -> None:
    """Upgrade schema."""
    # ---- new columns ----
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.add_column("documents", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "documents",
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column(
        "documents",
        "file_type",
        type_=sa.String(length=100),
        existing_type=sa.String(length=50),
        existing_nullable=False,
    )
    op.alter_column(
        "documents",
        "file_size",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "documents", "status", server_default="pending", existing_nullable=False
    )

    op.add_column(
        "document_chunks",
        sa.Column("token_estimate", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("messages", sa.Column("sources", sa.JSON(), nullable=True))

    # ---- timestamps: timezone-aware, defaulted by the database ----
    for table, column in TIMESTAMPS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            existing_nullable=False,
            server_default=sa.text("now()"),
        )

    # ---- cascades: deleting a user removes their documents, chunks and chats ----
    for name, table, column, referent in FOREIGN_KEYS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name, table, referent, [column], ["id"], ondelete="CASCADE"
        )

    # ---- indexes ----
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)

    op.create_unique_constraint(
        "uq_document_chunks_doc_index", "document_chunks", ["document_id", "chunk_index"]
    )

    # Approximate nearest-neighbour index for cosine similarity. HNSW gives good
    # recall without needing a populated table at build time (unlike ivfflat).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.drop_constraint("uq_document_chunks_doc_index", "document_chunks", type_="unique")

    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)

    for name, table, column, referent in reversed(FOREIGN_KEYS):
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, referent, [column], ["id"])

    for table, column in reversed(TIMESTAMPS):
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=None,
        )

    op.drop_column("messages", "sources")
    op.drop_column("document_chunks", "token_estimate")

    op.alter_column("documents", "status", server_default=None, existing_nullable=False)
    op.alter_column(
        "documents",
        "file_size",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )
    op.alter_column(
        "documents",
        "file_type",
        type_=sa.String(length=50),
        existing_type=sa.String(length=100),
        existing_nullable=False,
    )
    op.drop_column("documents", "chunk_count")
    op.drop_column("documents", "page_count")
    op.drop_column("documents", "error_message")

    op.drop_column("users", "is_admin")
    op.drop_column("users", "is_active")
