import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_project_role, require_task_project_role
from app.crud import activity as activity_crud
from app.db.session import get_db
from app.models.roles import Role
from app.models.task import Task
from app.models.user import User
from app.schemas.activity import ActivityLogListResponse

project_router = APIRouter(prefix="/api/projects/{project_id}/activity", tags=["activity"])
task_router = APIRouter(prefix="/api/tasks/{task_id}/activity", tags=["activity"])


@project_router.get("", response_model=ActivityLogListResponse)
async def list_project_activity(
    project_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_project_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
) -> ActivityLogListResponse:
    items, total = await activity_crud.list_by_project(
        db, project_id=project_id, page=page, page_size=page_size
    )
    return ActivityLogListResponse(items=items, total=total, page=page, page_size=page_size)


@task_router.get("", response_model=ActivityLogListResponse)
async def list_task_activity(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    task: Task = Depends(require_task_project_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
) -> ActivityLogListResponse:
    items, total = await activity_crud.list_by_task(
        db, task_id=task.id, page=page, page_size=page_size
    )
    return ActivityLogListResponse(items=items, total=total, page=page, page_size=page_size)
