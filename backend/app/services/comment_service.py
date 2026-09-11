import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import comment as comment_crud
from app.models.comment import Comment


async def create_comment(
    db: AsyncSession, *, task_id: uuid.UUID, author_id: uuid.UUID, body: str
) -> Comment:
    comment = await comment_crud.create(db, task_id=task_id, author_id=author_id, body=body)
    await db.commit()
    await db.refresh(comment)
    return comment
