"""Phase 3: activity_logs table

Revision ID: fd31448fb5dc
Revises: 3690234f411b
Create Date: 2026-08-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "fd31448fb5dc"
down_revision: str | None = "3690234f411b"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

activity_action = postgresql.ENUM(
    "project_created",
    "member_invited",
    "task_created",
    "task_updated",
    "task_deleted",
    "comment_added",
    "label_created",
    name="activity_action",
    create_type=False,
)


def upgrade() -> None:
    activity_action.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "activity_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("action", activity_action, nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("activity_metadata", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_activity_logs_project_id", "activity_logs", ["project_id"])
    op.create_index("ix_activity_logs_task_id", "activity_logs", ["task_id"])


def downgrade() -> None:
    op.drop_table("activity_logs")
    activity_action.drop(op.get_bind(), checkfirst=True)
