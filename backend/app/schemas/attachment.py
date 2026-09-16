import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    uploaded_by_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class AttachmentDownloadRead(BaseModel):
    download_url: str
    expires_in: int
