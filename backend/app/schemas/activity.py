import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.activity import ActivityAction


class ActivityLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None
    actor_id: uuid.UUID
    action: ActivityAction
    summary: str
    activity_metadata: dict | None
    created_at: datetime


class ActivityLogListResponse(BaseModel):
    items: list[ActivityLogRead]
    total: int
    page: int
    page_size: int
