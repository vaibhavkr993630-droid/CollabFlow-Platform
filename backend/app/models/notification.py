import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class NotificationType(StrEnum):
    MENTION = "mention"
    TASK_ASSIGNED = "task_assigned"
    WORKSPACE_INVITE = "workspace_invite"
    PROJECT_INVITE = "project_invite"
    TASK_DUE_SOON = "task_due_soon"


def _notification_type_column() -> SAEnum:
    return SAEnum(
        NotificationType,
        name="notification_type",
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
    )


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    type: Mapped[NotificationType] = mapped_column(_notification_type_column(), nullable=False)
    title: Mapped[str] = mapped_column(Text(), nullable=False)
    body: Mapped[str] = mapped_column(Text(), nullable=False)
    # Both ON DELETE SET NULL, same reasoning as ActivityLog.task_id: a notification
    # is a record of something that happened to the recipient and should survive the
    # referenced project/task being deleted later, not get destroyed or block it.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
