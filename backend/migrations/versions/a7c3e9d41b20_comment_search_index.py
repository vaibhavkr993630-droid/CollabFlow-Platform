"""Full-text search index for comments

Revision ID: a7c3e9d41b20
Revises: f17665be6383
Create Date: 2026-11-07

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a7c3e9d41b20"
down_revision: str | None = "f17665be6383"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# Must match app/crud/task.py (_comment_document) exactly, or Postgres will not use the
# index. Tasks get no search index on purpose: task search is always scoped to one
# project, so Postgres narrows by the existing project_id index first and never picks a
# text index there (checked with EXPLAIN). Comments are searched across a task's comments
# through an EXISTS subquery, where this index is used.
COMMENT_DOCUMENT = "to_tsvector('english', body)"


def upgrade() -> None:
    op.execute(
        f"CREATE INDEX ix_comments_search_document ON comments USING gin ({COMMENT_DOCUMENT})"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_comments_search_document")
