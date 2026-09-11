import uuid

from sqlalchemy import Column, ForeignKey, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

task_labels = Table(
    "task_labels",
    Base.metadata,
    Column("task_id", PGUUID(as_uuid=True), ForeignKey("tasks.id"), primary_key=True),
    Column("label_id", PGUUID(as_uuid=True), ForeignKey("labels.id"), primary_key=True),
)


class Label(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "labels"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#6b7280")

    tasks: Mapped[list["Task"]] = relationship(  # noqa: F821
        secondary=task_labels, back_populates="labels"
    )

    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_label_project_name"),)
