import uuid

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Attachment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attachments"

    # CASCADE, unlike ActivityLog/Notification's SET NULL: an attachment has no
    # meaning independent of its task — it's the actual file, not a record *about*
    # something. Deleting the task should take its files with it, not orphan them.
    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    # The object's key in the S3/MinIO bucket — not derived from filename alone
    # (see app/core/storage.build_storage_key), stored explicitly so deletion and
    # presigned-URL generation don't need to reconstruct it.
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
