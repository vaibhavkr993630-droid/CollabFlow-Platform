import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityAction, ActivityLog


async def create(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: ActivityAction,
    summary: str,
    task_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> ActivityLog:
    entry = ActivityLog(
        project_id=project_id,
        task_id=task_id,
        actor_id=actor_id,
        action=action,
        summary=summary,
        activity_metadata=metadata,
    )
    db.add(entry)
    await db.flush()
    return entry


async def list_by_project(
    db: AsyncSession, *, project_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[ActivityLog], int]:
    total = await db.scalar(
        select(func.count()).select_from(ActivityLog).where(ActivityLog.project_id == project_id)
    )
    result = await db.execute(
        select(ActivityLog)
        .where(ActivityLog.project_id == project_id)
        .order_by(ActivityLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total or 0


async def list_by_task(
    db: AsyncSession, *, task_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[ActivityLog], int]:
    total = await db.scalar(
        select(func.count()).select_from(ActivityLog).where(ActivityLog.task_id == task_id)
    )
    result = await db.execute(
        select(ActivityLog)
        .where(ActivityLog.task_id == task_id)
        .order_by(ActivityLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total or 0
