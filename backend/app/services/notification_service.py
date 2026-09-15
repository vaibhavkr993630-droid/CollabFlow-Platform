import uuid

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import notification as notification_crud
from app.crud import user as user_crud
from app.models.notification import Notification, NotificationType
from app.ws.events import publish_notification_event


async def create_and_dispatch(
    db: AsyncSession,
    redis: Redis,
    *,
    user_id: uuid.UUID,
    type: NotificationType,
    title: str,
    body: str,
    project_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
) -> Notification:
    """
    Persists the notification, commits it (its own unit of work — deliberately not
    bundled into the caller's transaction, since a notification about an action
    should exist once that action is durable, and this function may be called
    multiple times per caller, e.g. once per @mentioned user in a comment), then
    delivers it two ways: live over WebSocket if the recipient is connected, and
    always via a queued Celery email task regardless of connection state.
    """
    notification = await notification_crud.create(
        db,
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        project_id=project_id,
        task_id=task_id,
    )
    await db.commit()
    await db.refresh(notification)

    await publish_notification_event(
        redis,
        user_id=user_id,
        notification={
            "id": str(notification.id),
            "type": type.value,
            "title": title,
            "body": body,
            "project_id": str(project_id) if project_id else None,
            "task_id": str(task_id) if task_id else None,
            "created_at": notification.created_at.isoformat(),
        },
    )

    recipient = await user_crud.get_by_id(db, user_id)
    if recipient is not None:
        # Imported here, not at module level: app.workers.tasks pulls in Celery's
        # app registration machinery, which the API process doesn't otherwise need
        # to load at import time — this keeps that coupling one-directional.
        from app.workers.tasks import send_notification_email

        send_notification_email.delay(recipient.email, title, body)

    return notification
