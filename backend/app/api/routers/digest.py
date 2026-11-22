import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import digest
from app.assistant.client import AssistantClient, AssistantUnavailableError
from app.assistant.deps import require_assistant
from app.core.deps import require_project_role
from app.core.redis import get_redis_client
from app.db.session import get_db
from app.models.roles import Role
from app.models.user import User
from app.schemas.assistant import DigestRead, DigestRequest

router = APIRouter(prefix="/api/projects/{project_id}/digest", tags=["projects"])


@router.post("", response_model=DigestRead)
async def project_digest(
    project_id: uuid.UUID,
    body: DigestRequest,
    # Membership first: outsiders get 403 before anything is read or counted.
    current_user: User = Depends(require_project_role(Role.MEMBER)),
    client: AssistantClient = Depends(require_assistant),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
) -> DigestRead:
    """A short recap of what changed in the project over the last `days` days."""
    try:
        text, count, cached = await digest.project_digest(
            db, redis, client, project_id=project_id, days=body.days, user=current_user
        )
    except AssistantUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return DigestRead(digest=text, days=body.days, activity_count=count, cached=cached)
