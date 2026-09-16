import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import Attachment


async def get_by_id(db: AsyncSession, attachment_id: uuid.UUID) -> Attachment | None:
    return await db.get(Attachment, attachment_id)


async def create(
    db: AsyncSession,
    *,
    task_id: uuid.UUID,
    uploaded_by_id: uuid.UUID,
    filename: str,
    content_type: str,
    size_bytes: int,
    storage_key: str,
) -> Attachment:
    attachment = Attachment(
        task_id=task_id,
        uploaded_by_id=uploaded_by_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_key=storage_key,
    )
    db.add(attachment)
    await db.flush()
    return attachment


async def list_by_task(db: AsyncSession, *, task_id: uuid.UUID) -> list[Attachment]:
    result = await db.execute(
        select(Attachment).where(Attachment.task_id == task_id).order_by(Attachment.created_at)
    )
    return list(result.scalars().all())


async def delete(db: AsyncSession, attachment: Attachment) -> None:
    await db.delete(attachment)
    await db.flush()
