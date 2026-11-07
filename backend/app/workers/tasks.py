import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.email import send_email
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.send_notification_email")
def send_notification_email(
    to_email: str, subject: str, body: str, html_body: str | None = None
) -> None:
    send_email(to_email=to_email, subject=subject, body=body, html_body=html_body)


@asynccontextmanager
async def job_resources() -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], Redis]]:
    """
    A fresh database engine and Redis client for one background job, closed when the job ends.

    Why not reuse the API's shared engine (app/db/session.py) and Redis client
    (app/core/redis.py)? A Celery task is sync, so each job enters async code through
    asyncio.run(), which creates a brand-new event loop and closes it afterwards. Pooled
    asyncpg connections and the cached Redis client stay bound to the loop that created
    them, so the *second* job in the same worker process failed with "attached to a
    different loop". The API process never hits this because it runs one loop for its
    whole life. NullPool means no connection outlives the job; tests/conftest.py fixes the
    same problem the same way for pytest's per-test loops.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield (
            async_sessionmaker(
                bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
            ),
            redis,
        )
    finally:
        await redis.aclose()
        await engine.dispose()


@celery_app.task(name="app.workers.tasks.send_due_soon_reminders")
def send_due_soon_reminders() -> None:
    """Celery Beat entrypoint (sync) — bridges into the app's async DB/Redis stack
    via asyncio.run(), the standard way to call async code from a sync Celery task."""
    asyncio.run(_send_due_soon_reminders_async())


async def _send_due_soon_reminders_async() -> None:
    # Imported lazily, mirroring notification_service's import of this module: the
    # worker process needs the full app/db/ws stack, but importing it at module
    # level here would pull that stack into the Celery app registration path too.
    from app.crud import task as task_crud
    from app.models.notification import NotificationType
    from app.services import notification_service

    tomorrow = date.today() + timedelta(days=1)

    async with job_resources() as (session_factory, redis), session_factory() as db:
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
