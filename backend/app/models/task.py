import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy import Date as SADate
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TaskSortField(StrEnum):
    CREATED_AT = "created_at"
    DUE_DATE = "due_date"
    PRIORITY = "priority"
    STATUS = "status"
    POSITION = "position"
    TITLE = "title"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


def _task_status_column() -> SAEnum:
    return SAEnum(
        TaskStatus,
        name="task_status",
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
    )


def _task_priority_column() -> SAEnum:
    return SAEnum(
        TaskPriority,
        name="task_priority",
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
    )


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        _task_status_column(), nullable=False, default=TaskStatus.TODO, index=True
    )
    priority: Mapped[TaskPriority] = mapped_column(
        _task_priority_column(), nullable=False, default=TaskPriority.MEDIUM
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    due_date: Mapped[date | None] = mapped_column(SADate(), nullable=True)
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True, index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    # Fractional ordering within a status column, for stable Kanban drag-and-drop
    # without needing to renumber every row on each reorder.
    position: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)

    subtasks: Mapped[list["Task"]] = relationship(
        back_populates="parent_task", cascade="all, delete-orphan"
    )
    parent_task: Mapped["Task | None"] = relationship(
        back_populates="subtasks", remote_side="Task.id"
    )
    labels: Mapped[list["Label"]] = relationship(  # noqa: F821
        secondary="task_labels", back_populates="tasks", lazy="selectin"
    )
    comments: Mapped[list["Comment"]] = relationship(  # noqa: F821
        back_populates="task", cascade="all, delete-orphan"
    )
