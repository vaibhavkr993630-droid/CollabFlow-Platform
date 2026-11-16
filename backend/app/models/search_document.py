import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Length of each stored meaning vector. Part of the column type, so changing it needs a new
# migration and a full re-index. 768 kept search quality equal to the full 3072 in testing.
EMBEDDING_DIMENSIONS = 768


class SearchDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A searchable copy of one task's or one comment's text, plus a vector that captures its
    meaning. Kept up to date by background jobs (app/assistant/indexing.py). Only exists when
    the database has the pgvector extension; without it, search by meaning stays off.
    """

    __tablename__ = "search_documents"

    # "task:<id>" or "comment:<id>": one row per source, so updates replace in place.
    source_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    # Every search filters on this first, so results never leave the project.
    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    # CASCADE: deleting a task or comment removes its searchable copy in the same statement.
    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    comment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("comments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    # SHA-256 of `content`: unchanged text is never sent to the provider again.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
