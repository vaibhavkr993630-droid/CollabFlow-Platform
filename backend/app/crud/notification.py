import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType


async def create(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    type: NotificationType,
    title: str,
    body: str,
    project_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id, type=type, title=title, body=body, project_id=project_id, task_id=task_id
    )
    db.add(notification)
    await db.flush()
    return notification


async def get_by_id(db: AsyncSession, notification_id: uuid.UUID) -> Notification | None:
    return await db.get(Notification, notification_id)


async def list_by_user(
    db: AsyncSession, *, user_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[Notification], int]:
    total = await db.scalar(
        select(func.count()).select_from(Notification).where(Notification.user_id == user_id)
    )
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total or 0


async def unread_count(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    count = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    return count or 0


async def mark_read(db: AsyncSession, notification: Notification) -> Notification:
    notification.read_at = datetime.now(UTC)
    await db.flush()
    return notification


async def mark_all_read(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    unread = list(result.scalars().all())
    now = datetime.now(UTC)
    for notification in unread:
        notification.read_at = now
    await db.flush()
    return len(unread)
