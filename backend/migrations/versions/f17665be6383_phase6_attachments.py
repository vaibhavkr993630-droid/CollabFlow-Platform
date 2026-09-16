"""Phase 6: attachments table + attachment activity actions

Revision ID: f17665be6383
Revises: c18c809922b5
Create Date: 2026-08-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f17665be6383"
down_revision: str | None = "c18c809922b5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # New ActivityAction values. Postgres 12+ allows ALTER TYPE ... ADD VALUE inside
    # a transaction (which Alembic wraps this migration in) as long as the new value
    # isn't used in the same transaction — true here, so no special handling needed.
    op.execute("ALTER TYPE activity_action ADD VALUE IF NOT EXISTS 'attachment_added'")
    op.execute("ALTER TYPE activity_action ADD VALUE IF NOT EXISTS 'attachment_removed'")

    op.create_table(
        "attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(1000), nullable=False, unique=True),
    )
    op.create_index("ix_attachments_task_id", "attachments", ["task_id"])


def downgrade() -> None:
    op.drop_table("attachments")
    # Postgres has no ALTER TYPE ... DROP VALUE — removing the two enum values added
    # above would require rebuilding the type (create new, migrate columns, drop old).
    # Not worth the churn for a downgrade path; the extra enum values are harmless to
    # leave in place if this migration is ever rolled back.
