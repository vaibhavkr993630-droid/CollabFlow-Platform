import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import task_drafts
from app.assistant.client import AssistantClient, AssistantUnavailableError
from app.assistant.deps import require_assistant
from app.core.deps import require_project_role
from app.core.redis import get_redis_client
from app.db.session import get_db
from app.models.roles import Role
from app.models.user import User
from app.schemas.assistant import TaskDraftsRead, TaskDraftsRequest

router = APIRouter(prefix="/api/projects/{project_id}/task-drafts", tags=["tasks"])


@router.post("", response_model=TaskDraftsRead)
async def draft_tasks_from_notes(
    project_id: uuid.UUID,
    body: TaskDraftsRequest,
    # Membership first: outsiders get 403 before anything else happens.
    current_user: User = Depends(require_project_role(Role.MEMBER)),
    client: AssistantClient = Depends(require_assistant),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
) -> TaskDraftsRead:
    """
    Proposes tasks from pasted notes. Saves nothing: the user reviews the drafts and the
    frontend creates the chosen ones through the normal task endpoint, so permissions,
    the activity log and live updates all apply as usual.
    """
    try:
        drafts = await task_drafts.draft_tasks(
            db, redis, client, project_id=project_id, text=body.text, user=current_user
        )
    except AssistantUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return TaskDraftsRead(drafts=drafts)
