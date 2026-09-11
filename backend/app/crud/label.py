import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.label import Label


async def get_by_id(db: AsyncSession, label_id: uuid.UUID) -> Label | None:
    return await db.get(Label, label_id)


async def create(db: AsyncSession, *, project_id: uuid.UUID, name: str, color: str) -> Label:
    label = Label(project_id=project_id, name=name, color=color)
    db.add(label)
    await db.flush()
    return label


async def list_by_project(db: AsyncSession, *, project_id: uuid.UUID) -> list[Label]:
    result = await db.execute(select(Label).where(Label.project_id == project_id))
    return list(result.scalars().all())
