import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.roles import Role


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    workspace_id: uuid.UUID


class ProjectMemberInvite(BaseModel):
    email: EmailStr
    role: Role = Role.MEMBER


class ProjectMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    role: Role


class PresenceRead(BaseModel):
    online_user_ids: list[str]
