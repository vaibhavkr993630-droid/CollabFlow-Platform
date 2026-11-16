"""Searchable copies of task and comment text, with meaning vectors (pgvector)

Revision ID: c4e8b2a91d53
Revises: a7c3e9d41b20
Create Date: 2026-11-15

"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "c4e8b2a91d53"
down_revision: str | None = "a7c3e9d41b20"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

EMBEDDING_DIMENSIONS = 768  # must match app/models/search_document.py


def upgrade() -> None:
    # Hosted Postgres does not always ship pgvector. Skipping (instead of failing) keeps the
    # app deployable anywhere; search by meaning then simply stays off.
    available = op.get_bind().execute(
        sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
    ).scalar()
    if not available:
        logger.warning("pgvector is not available: skipping search_documents")
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "search_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_key", sa.String(length=80), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("comment_id", sa.UUID(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["comment_id"], ["comments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key"),
    )
    op.create_index("ix_search_documents_project_id", "search_documents", ["project_id"])
    op.create_index("ix_search_documents_task_id", "search_documents", ["task_id"])
    op.create_index("ix_search_documents_comment_id", "search_documents", ["comment_id"])
    # No vector index on purpose: every search is limited to one project (a few hundred rows
    # at most), where an exact scan is fast and, unlike an approximate index combined with a
    # project filter, never silently returns fewer results.


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS search_documents")
