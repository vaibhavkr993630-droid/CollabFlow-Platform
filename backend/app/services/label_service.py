import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import label as label_crud
from app.models.label import Label


class LabelServiceError(Exception):
    """Raised for invalid-state cases — mapped to 4xx at the router."""


async def create_label(db: AsyncSession, *, project_id: uuid.UUID, name: str, color: str) -> Label:
    try:
        label = await label_crud.create(db, project_id=project_id, name=name, color=color)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise LabelServiceError("A label with this name already exists in this project") from exc

    await db.refresh(label)
    return label
