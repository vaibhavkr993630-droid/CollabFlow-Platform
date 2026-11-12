from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import summaries
from app.assistant.client import AssistantClient, AssistantUnavailableError
from app.assistant.deps import require_assistant
from app.core.deps import get_current_user, require_task_project_role
from app.core.redis import get_redis_client
from app.db.session import get_db
from app.models.roles import Role
from app.models.task import Task
from app.models.user import User
from app.schemas.assistant import ThreadSummaryRead

router = APIRouter(prefix="/api/tasks/{task_id}/comments", tags=["comments"])


@router.post("/summary", response_model=ThreadSummaryRead)
async def summarize_comments(
    # Order matters: membership is checked before anything else, so outsiders get 403/404
    # and never learn whether the feature is on.
    task: Task = Depends(require_task_project_role(Role.MEMBER)),
    current_user: User = Depends(get_current_user),
    client: AssistantClient = Depends(require_assistant),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
) -> ThreadSummaryRead:
    try:
        summary, count, cached = await summaries.summarize_thread(
            db, redis, client, task=task, user=current_user
        )
    except summaries.ThreadTooShortError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AssistantUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return ThreadSummaryRead(summary=summary, comment_count=count, cached=cached)
