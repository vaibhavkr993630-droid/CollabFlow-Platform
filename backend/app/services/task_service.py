import uuid
from datetime import date

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import label as label_crud
from app.crud import project as project_crud
from app.crud import task as task_crud
from app.models.activity import ActivityAction
from app.models.task import Task, TaskPriority, TaskStatus
from app.services import activity_service
from app.ws.events import WSEventType, publish_event


class TaskServiceError(Exception):
    """Raised for not-found or invalid-state cases — mapped to 4xx at the router."""


async def _validate_assignee(
    db: AsyncSession, *, project_id: uuid.UUID, assignee_id: uuid.UUID
) -> None:
    membership = await project_crud.get_membership(db, project_id=project_id, user_id=assignee_id)
    if membership is None:
        raise TaskServiceError("Assignee must be a member of this project")


def _task_broadcast_payload(task: Task) -> dict:
    return {
        "id": str(task.id),
        "title": task.title,
        "status": task.status.value,
        "priority": task.priority.value,
        "assignee_id": str(task.assignee_id) if task.assignee_id else None,
        "position": task.position,
    }


async def create_task(
    db: AsyncSession,
    redis: Redis,
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
    await activity_service.log(
        db,
        project_id=project_id,
        task_id=task.id,
        actor_id=created_by_id,
        action=ActivityAction.TASK_CREATED,
        summary=f"created task '{title}'",
    )
    await db.commit()
    await db.refresh(task)

    await publish_event(
        redis,
        project_id=project_id,
        event_type=WSEventType.TASK_CREATED,
        data=_task_broadcast_payload(task),
        actor_id=created_by_id,
    )
    return task


async def _resolve_labels(
    db: AsyncSession, *, project_id: uuid.UUID, label_ids: list[uuid.UUID]
) -> list:
    labels = []
    for label_id in label_ids:
        label = await label_crud.get_by_id(db, label_id)
        if label is None or label.project_id != project_id:
            raise TaskServiceError("Label must belong to the same project as the task")
        labels.append(label)
    return labels


async def update_task(
    db: AsyncSession, redis: Redis, *, task: Task, updates: dict, actor_id: uuid.UUID
) -> Task:
    if "assignee_id" in updates and updates["assignee_id"] is not None:
        await _validate_assignee(db, project_id=task.project_id, assignee_id=updates["assignee_id"])

    label_ids = updates.pop("label_ids", None)

    changes = {}
    for field, new_value in updates.items():
        old_value = getattr(task, field)
        if old_value != new_value:
            changes[field] = {"old": str(old_value), "new": str(new_value)}
        setattr(task, field, new_value)

    if label_ids is not None:
        old_label_names = sorted(label.name for label in task.labels)
        task.labels = await _resolve_labels(db, project_id=task.project_id, label_ids=label_ids)
        new_label_names = sorted(label.name for label in task.labels)
        if old_label_names != new_label_names:
            changes["labels"] = {"old": old_label_names, "new": new_label_names}

    if changes:
        changed_fields = ", ".join(sorted(changes))
        await activity_service.log(
            db,
            project_id=task.project_id,
            task_id=task.id,
            actor_id=actor_id,
            action=ActivityAction.TASK_UPDATED,
            summary=f"updated task '{task.title}' ({changed_fields})",
            metadata={"changes": changes},
        )

    await db.commit()
    await db.refresh(task)

    if changes:
        await publish_event(
            redis,
            project_id=task.project_id,
            event_type=WSEventType.TASK_UPDATED,
            data={**_task_broadcast_payload(task), "changes": changes},
            actor_id=actor_id,
        )
    return task


async def delete_task(db: AsyncSession, redis: Redis, *, task: Task, actor_id: uuid.UUID) -> None:
    task_id, project_id, title = task.id, task.project_id, task.title

    await activity_service.log(
        db,
        project_id=project_id,
        task_id=None,  # the task row is about to be deleted — don't leave a dangling FK
        actor_id=actor_id,
        action=ActivityAction.TASK_DELETED,
        summary=f"deleted task '{title}'",
    )
    await task_crud.delete(db, task)
    await db.commit()

    await publish_event(
        redis,
        project_id=project_id,
        event_type=WSEventType.TASK_DELETED,
        data={"id": str(task_id), "title": title},
        actor_id=actor_id,
    )
