import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.models.task import TaskPriority


class ThreadSummaryRead(BaseModel):
    summary: str
    comment_count: int
    cached: bool


class TaskDraftsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class TaskDraft(BaseModel):
    """A proposed task. Nothing is saved until the user confirms it in the UI."""

    title: str
    description: str | None
    priority: TaskPriority
    assignee_id: uuid.UUID | None
    due_date: date | None


class TaskDraftsRead(BaseModel):
    drafts: list[TaskDraft]
