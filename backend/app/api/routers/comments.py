from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_task_project_role
from app.crud import comment as comment_crud
from app.db.session import get_db
from app.models.comment import Comment
from app.models.roles import Role
from app.models.task import Task
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentRead
from app.services import comment_service

router = APIRouter(prefix="/api/tasks/{task_id}/comments", tags=["comments"])


@router.post("", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
async def create_comment(
    comment_in: CommentCreate,
    task: Task = Depends(require_task_project_role(Role.MEMBER)),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Comment:
    return await comment_service.create_comment(
        db, task_id=task.id, author_id=current_user.id, body=comment_in.body
    )


@router.get("", response_model=list[CommentRead])
async def list_comments(
    task: Task = Depends(require_task_project_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
) -> list[Comment]:
    return await comment_crud.list_by_task(db, task_id=task.id)
