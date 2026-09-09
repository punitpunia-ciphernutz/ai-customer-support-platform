"""Add FTS columns + GIN index on document_chunks for keyword retrieval.

Revision ID: 0013_document_chunks_fts
Revises: 0012_document_chunks_hnsw
Create Date: 2026-09-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_document_chunks_fts"
down_revision: Union[str, None] = "0012_document_chunks_hnsw"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("search_document", sa.Text(), nullable=True))
    op.add_column(
        "document_chunks",
        sa.Column("search_tsv", postgresql.TSVECTOR(), nullable=True),
    )

    # Backfill title + content; use simple config so error codes / IDs are not over-stemmed.
    op.execute(
        """
        UPDATE document_chunks AS c
        SET
            search_document = COALESCE(d.title, '') || ' ' || COALESCE(c.content, ''),
            search_tsv = to_tsvector(
                'simple',
                COALESCE(d.title, '') || ' ' || COALESCE(c.content, '')
            )
        FROM documents AS d
        WHERE d.id = c.document_id
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION document_chunks_search_tsv_trigger()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.search_document IS NOT NULL THEN
                NEW.search_tsv := to_tsvector('simple', NEW.search_document);
            ELSE
                NEW.search_tsv := NULL;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_document_chunks_search_tsv ON document_chunks;
        CREATE TRIGGER trg_document_chunks_search_tsv
        BEFORE INSERT OR UPDATE OF search_document, content
        ON document_chunks
        FOR EACH ROW
        EXECUTE FUNCTION document_chunks_search_tsv_trigger();
        """
    )

    # GIN index — CONCURRENTLY outside a transaction.
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_document_chunks_search_tsv
            ON document_chunks
            USING gin (search_tsv)
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_document_chunks_search_tsv")

    op.execute("DROP TRIGGER IF EXISTS trg_document_chunks_search_tsv ON document_chunks")
    op.execute("DROP FUNCTION IF EXISTS document_chunks_search_tsv_trigger()")
    op.drop_column("document_chunks", "search_tsv")
    op.drop_column("document_chunks", "search_document")
