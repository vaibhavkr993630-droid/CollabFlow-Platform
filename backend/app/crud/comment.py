import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment


async def get_by_id(db: AsyncSession, comment_id: uuid.UUID) -> Comment | None:
    return await db.get(Comment, comment_id)


async def create(
    db: AsyncSession, *, task_id: uuid.UUID, author_id: uuid.UUID, body: str
) -> Comment:
    comment = Comment(task_id=task_id, author_id=author_id, body=body)
    db.add(comment)
    await db.flush()
    return comment


async def list_by_task(db: AsyncSession, *, task_id: uuid.UUID) -> list[Comment]:
    result = await db.execute(
        select(Comment).where(Comment.task_id == task_id).order_by(Comment.created_at)
    )
    return list(result.scalars().all())
