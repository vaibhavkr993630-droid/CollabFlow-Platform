import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.models.task import TaskPriority, TaskStatus


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


class SimilarTask(BaseModel):
    """A top-level task close in meaning to the query, with the text that matched best."""

    id: uuid.UUID
    title: str
    status: TaskStatus
    priority: TaskPriority
    similarity: float
    matched_in: str  # "task" or "comment"
    matched_text: str


class SimilarTasksRead(BaseModel):
    results: list[SimilarTask]
