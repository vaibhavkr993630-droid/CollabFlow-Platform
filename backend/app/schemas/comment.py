import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime
    updated_at: datetime
