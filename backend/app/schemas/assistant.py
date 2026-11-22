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


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class AskSource(BaseModel):
    """A task or comment the answer cited as [number]."""

    number: int
    task_id: uuid.UUID
    task_title: str
    kind: str  # "task" or "comment"
    snippet: str


class AskRead(BaseModel):
    answer: str
    sources: list[AskSource]


class DigestRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=30)


class DigestRead(BaseModel):
    digest: str
    days: int
    activity_count: int
    cached: bool
