import uuid
from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ActivityAction(StrEnum):
    PROJECT_CREATED = "project_created"
    MEMBER_INVITED = "member_invited"
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_DELETED = "task_deleted"
    COMMENT_ADDED = "comment_added"
    LABEL_CREATED = "label_created"
    ATTACHMENT_ADDED = "attachment_added"
    ATTACHMENT_REMOVED = "attachment_removed"


def _activity_action_column() -> SAEnum:
    return SAEnum(
        ActivityAction,
        name="activity_action",
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
    )


class ActivityLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Append-only. Rows are never updated or deleted — only ever inserted by
    app/services/activity_service.py, called from other services after a
    state-changing action commits successfully.
    """

    __tablename__ = "activity_logs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    # ON DELETE SET NULL: a task's activity history should outlive the task itself —
    # deleting a task must not be blocked by, or cascade-destroy, its project's audit trail.
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    action: Mapped[ActivityAction] = mapped_column(_activity_action_column(), nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    activity_metadata: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)
