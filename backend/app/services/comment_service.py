import uuid

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mentions import extract_mentioned_emails
from app.crud import comment as comment_crud
from app.crud import project as project_crud
from app.crud import task as task_crud
from app.crud import user as user_crud
from app.models.activity import ActivityAction
from app.models.comment import Comment
from app.models.notification import NotificationType
from app.models.task import Task
from app.services import activity_service, notification_service
from app.ws.events import WSEventType, publish_event


async def _notify_mentions(
    db: AsyncSession, redis: Redis, *, body: str, task: Task, author_id: uuid.UUID
) -> None:
    for email in extract_mentioned_emails(body):
        mentioned_user = await user_crud.get_by_email(db, email)
        if mentioned_user is None or mentioned_user.id == author_id:
            continue

        # Only notify if the mentioned user is actually a member of this task's
        # project — otherwise a comment body could be used to probe whether an
        # arbitrary email address has an account, or spam-notify strangers.
        membership = await project_crud.get_membership(
            db, project_id=task.project_id, user_id=mentioned_user.id
        )
        if membership is None:
            continue

        await notification_service.create_and_dispatch(
            db,
            redis,
            user_id=mentioned_user.id,
            type=NotificationType.MENTION,
            title=f"You were mentioned in '{task.title}'",
            body=f"You were mentioned in a comment on '{task.title}'.",
            project_id=task.project_id,
            task_id=task.id,
        )


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

    await _notify_mentions(db, redis, body=comment.body, task=task, author_id=author_id)
    return comment
