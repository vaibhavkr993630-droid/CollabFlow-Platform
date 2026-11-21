import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import ask, indexing
from app.assistant.client import AssistantClient, AssistantUnavailableError
from app.assistant.deps import enforce_daily_limit, require_assistant
from app.core.deps import require_project_role
from app.core.redis import get_redis_client
from app.db.session import get_db
from app.models.roles import Role
from app.models.user import User
from app.schemas.assistant import AskRead, AskRequest

router = APIRouter(prefix="/api/projects/{project_id}/ask", tags=["projects"])


@router.post("", response_model=AskRead)
async def ask_project(
    project_id: uuid.UUID,
    body: AskRequest,
    # Membership first: outsiders get 403 before anything is retrieved or counted.
    current_user: User = Depends(require_project_role(Role.MEMBER)),
    client: AssistantClient = Depends(require_assistant),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
) -> AskRead:
    """Answers a question from this project's own tasks and comments, with cited sources."""
    if not await indexing.is_ready(db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Asking questions is not available on this server.",
        )
    await enforce_daily_limit(current_user=current_user, redis=redis)
    try:
        answer, sources = await ask.ask_project(
            db, client, project_id=project_id, question=body.question.strip()
        )
    except AssistantUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return AskRead(answer=answer, sources=sources)
