import asyncio
from datetime import date, timedelta

from app.core.email import send_email
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.send_notification_email")
def send_notification_email(to_email: str, subject: str, body: str) -> None:
    send_email(to_email=to_email, subject=subject, body=body)


@celery_app.task(name="app.workers.tasks.send_due_soon_reminders")
def send_due_soon_reminders() -> None:
    """Celery Beat entrypoint (sync) — bridges into the app's async DB/Redis stack
    via asyncio.run(), the standard way to call async code from a sync Celery task."""
    asyncio.run(_send_due_soon_reminders_async())


async def _send_due_soon_reminders_async() -> None:
    # Imported lazily, mirroring notification_service's import of this module: the
    # worker process needs the full app/db/ws stack, but importing it at module
    # level here would pull that stack into the Celery app registration path too.
    from app.core.redis import get_redis_client
    from app.crud import task as task_crud
    from app.db.session import AsyncSessionLocal
    from app.models.notification import NotificationType
    from app.services import notification_service

    tomorrow = date.today() + timedelta(days=1)
    redis = get_redis_client()

    async with AsyncSessionLocal() as db:
        due_soon = await task_crud.list_due_on(db, due_date=tomorrow)
        for task in due_soon:
            await notification_service.create_and_dispatch(
                db,
                redis,
                user_id=task.assignee_id,
                type=NotificationType.TASK_DUE_SOON,
                title=f"'{task.title}' is due tomorrow",
                body=f"Task '{task.title}' is due on {task.due_date.isoformat()}.",
                project_id=task.project_id,
                task_id=task.id,
            )
