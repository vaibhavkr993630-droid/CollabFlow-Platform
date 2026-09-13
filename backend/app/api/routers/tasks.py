import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_project_role, require_task_project_role
from app.crud import task as task_crud
from app.db.session import get_db
from app.models.roles import Role
from app.models.task import SortOrder, Task, TaskPriority, TaskSortField, TaskStatus
from app.models.user import User
from app.schemas.task import TaskCreate, TaskListResponse, TaskRead, TaskUpdate
from app.services import task_service
from app.services.task_service import TaskServiceError

project_router = APIRouter(prefix="/api/projects/{project_id}/tasks", tags=["tasks"])
task_router = APIRouter(prefix="/api/tasks/{task_id}", tags=["tasks"])


@project_router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    project_id: uuid.UUID,
    task_in: TaskCreate,
    current_user: User = Depends(require_project_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
) -> Task:
    try:
        return await task_service.create_task(
            db,
            project_id=project_id,
            title=task_in.title,
            description=task_in.description,
            status=task_in.status,
            priority=task_in.priority,
            assignee_id=task_in.assignee_id,
            due_date=task_in.due_date,
            parent_task_id=task_in.parent_task_id,
            created_by_id=current_user.id,
        )
    except TaskServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@project_router.get("", response_model=TaskListResponse)
async def list_tasks(
    project_id: uuid.UUID,
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    priority: TaskPriority | None = None,
    assignee_id: uuid.UUID | None = None,
    label_id: uuid.UUID | None = None,
    search: str | None = Query(default=None, max_length=500),
    sort_by: TaskSortField = TaskSortField.POSITION,
    sort_order: SortOrder = SortOrder.ASC,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_project_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
) -> TaskListResponse:
    items, total = await task_crud.list_by_project(
        db,
        project_id=project_id,
        status=status_filter,
        priority=priority,
        assignee_id=assignee_id,
        label_id=label_id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return TaskListResponse(items=items, total=total, page=page, page_size=page_size)


@task_router.get("", response_model=TaskRead)
async def get_task(task: Task = Depends(require_task_project_role(Role.MEMBER))) -> Task:
    return task


@task_router.patch("", response_model=TaskRead)
async def update_task(
    task_in: TaskUpdate,
    task: Task = Depends(require_task_project_role(Role.MEMBER)),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Task:
    updates = task_in.model_dump(exclude_unset=True)
    try:
        return await task_service.update_task(
            db, task=task, updates=updates, actor_id=current_user.id
        )
    except TaskServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@task_router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task: Task = Depends(require_task_project_role(Role.ADMIN)),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await task_service.delete_task(db, task=task, actor_id=current_user.id)


@task_router.get("/subtasks", response_model=list[TaskRead])
async def list_subtasks(
    task: Task = Depends(require_task_project_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
) -> list[Task]:
    return await task_crud.list_subtasks(db, parent_task_id=task.id)
