import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import project as project_crud
from app.crud import task as task_crud
from app.models.task import Task, TaskPriority, TaskStatus


class TaskServiceError(Exception):
    """Raised for not-found or invalid-state cases — mapped to 4xx at the router."""


async def _validate_assignee(
    db: AsyncSession, *, project_id: uuid.UUID, assignee_id: uuid.UUID
) -> None:
    membership = await project_crud.get_membership(db, project_id=project_id, user_id=assignee_id)
    if membership is None:
        raise TaskServiceError("Assignee must be a member of this project")


async def create_task(
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
    if assignee_id is not None:
        await _validate_assignee(db, project_id=project_id, assignee_id=assignee_id)

    if parent_task_id is not None:
        parent = await task_crud.get_by_id(db, parent_task_id)
        if parent is None or parent.project_id != project_id:
            raise TaskServiceError("Parent task must belong to the same project")

    task = await task_crud.create(
        db,
        project_id=project_id,
        title=title,
        description=description,
        status=status,
        priority=priority,
        assignee_id=assignee_id,
        due_date=due_date,
        parent_task_id=parent_task_id,
        created_by_id=created_by_id,
    )
    await db.commit()
    await db.refresh(task)
    return task


async def update_task(db: AsyncSession, *, task: Task, updates: dict) -> Task:
    if "assignee_id" in updates and updates["assignee_id"] is not None:
        await _validate_assignee(db, project_id=task.project_id, assignee_id=updates["assignee_id"])

    for field, value in updates.items():
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, *, task: Task) -> None:
    await task_crud.delete(db, task)
    await db.commit()
