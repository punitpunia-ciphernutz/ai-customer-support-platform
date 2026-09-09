"""Add HNSW index on document_chunks.embedding for ANN cosine search.

Revision ID: 0012_document_chunks_hnsw
Revises: 0011_chat_widgets
Create Date: 2026-09-09
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0012_document_chunks_hnsw"
down_revision: Union[str, None] = "0011_chat_widgets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Match Settings defaults (hnsw_m / hnsw_ef_construction). Changing these
# requires a new migration that rebuilds the index.
_HNSW_M = 16
_HNSW_EF_CONSTRUCTION = 64


def upgrade() -> None:
    # CONCURRENTLY cannot run inside a transaction.
    with op.get_context().autocommit_block():
        op.execute(
            f"""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_document_chunks_embedding_hnsw
            ON document_chunks
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = {_HNSW_M}, ef_construction = {_HNSW_EF_CONSTRUCTION})
            WHERE embedding IS NOT NULL
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_document_chunks_embedding_hnsw")
