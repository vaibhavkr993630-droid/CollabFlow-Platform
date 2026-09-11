import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskPriority, TaskStatus


async def get_by_id(db: AsyncSession, task_id: uuid.UUID) -> Task | None:
    return await db.get(Task, task_id)


async def create(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    title: str,
    description: str | None,
    status: TaskStatus,
    priority: TaskPriority,
    assignee_id: uuid.UUID | None,
    due_date: date | None,
    parent_task_id: uuid.UUID | None,
    created_by_id: uuid.UUID,
) -> Task:
    # New tasks go to the end of their status column — position is the max existing
    # position in that (project, status) bucket, plus one.
    max_position = await db.scalar(
        select(func.max(Task.position)).where(
            Task.project_id == project_id, Task.status == status
        )
    )
    task = Task(
        project_id=project_id,
        title=title,
        description=description,
        status=status,
        priority=priority,
        assignee_id=assignee_id,
        due_date=due_date,
        parent_task_id=parent_task_id,
        created_by_id=created_by_id,
        position=(max_position or 0) + 1,
    )
    db.add(task)
    await db.flush()
    return task


async def list_by_project(db: AsyncSession, *, project_id: uuid.UUID) -> list[Task]:
    result = await db.execute(
        select(Task)
        .where(Task.project_id == project_id, Task.parent_task_id.is_(None))
        .order_by(Task.status, Task.position)
    )
    return list(result.scalars().all())


async def list_subtasks(db: AsyncSession, *, parent_task_id: uuid.UUID) -> list[Task]:
    result = await db.execute(
        select(Task).where(Task.parent_task_id == parent_task_id).order_by(Task.position)
    )
    return list(result.scalars().all())


async def delete(db: AsyncSession, task: Task) -> None:
    await db.delete(task)
    await db.flush()
