import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import label as label_crud
from app.models.activity import ActivityAction
from app.models.label import Label
from app.services import activity_service


class LabelServiceError(Exception):
    """Raised for invalid-state cases — mapped to 4xx at the router."""


async def create_label(
    db: AsyncSession, *, project_id: uuid.UUID, name: str, color: str, actor_id: uuid.UUID
) -> Label:
    try:
        label = await label_crud.create(db, project_id=project_id, name=name, color=color)
        await activity_service.log(
            db,
            project_id=project_id,
            actor_id=actor_id,
            action=ActivityAction.LABEL_CREATED,
            summary=f"created label '{name}'",
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise LabelServiceError("A label with this name already exists in this project") from exc

    await db.refresh(label)
    return label
