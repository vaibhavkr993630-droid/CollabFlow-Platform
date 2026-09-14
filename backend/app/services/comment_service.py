import uuid

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import comment as comment_crud
from app.crud import task as task_crud
from app.models.activity import ActivityAction
from app.models.comment import Comment
from app.services import activity_service
from app.ws.events import WSEventType, publish_event


async def create_comment(
    db: AsyncSession, redis: Redis, *, task_id: uuid.UUID, author_id: uuid.UUID, body: str
) -> Comment:
    comment = await comment_crud.create(db, task_id=task_id, author_id=author_id, body=body)

    task = await task_crud.get_by_id(db, task_id)
    await activity_service.log(
        db,
        project_id=task.project_id,
        task_id=task_id,
        actor_id=author_id,
        action=ActivityAction.COMMENT_ADDED,
        summary=f"commented on '{task.title}'",
    )

    await db.commit()
    await db.refresh(comment)

    await publish_event(
        redis,
        project_id=task.project_id,
        event_type=WSEventType.COMMENT_CREATED,
        data={
            "id": str(comment.id),
            "task_id": str(task_id),
            "author_id": str(author_id),
            "body": comment.body,
        },
        actor_id=author_id,
    )
    return comment
