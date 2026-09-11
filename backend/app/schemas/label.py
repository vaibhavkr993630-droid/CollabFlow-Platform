import re
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class LabelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(default="#6b7280")

    @field_validator("color")
    @classmethod
    def validate_hex_color(cls, value: str) -> str:
        if not _HEX_COLOR_RE.match(value):
            raise ValueError("color must be a hex string like #6b7280")
        return value


class LabelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    color: str
