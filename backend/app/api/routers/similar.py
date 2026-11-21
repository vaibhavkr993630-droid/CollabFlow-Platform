import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import indexing, similar
from app.assistant.client import AssistantClient, AssistantUnavailableError
from app.assistant.deps import enforce_search_limit, require_assistant
from app.core.deps import require_project_role
from app.db.session import get_db
from app.models.roles import Role
from app.models.user import User
from app.schemas.assistant import SimilarTasksRead

router = APIRouter(prefix="/api/projects/{project_id}/tasks/similar", tags=["tasks"])


@router.get("", response_model=SimilarTasksRead)
async def find_similar_tasks(
    project_id: uuid.UUID,
    q: str = Query(min_length=3, max_length=500),
    purpose: Literal["search", "duplicate"] = "search",
    # Membership first: outsiders get 403 before anything else happens.
    _member: User = Depends(require_project_role(Role.MEMBER)),
    client: AssistantClient = Depends(require_assistant),
    db: AsyncSession = Depends(get_db),
    _limited: User = Depends(enforce_search_limit),
) -> SimilarTasksRead:
    """
    Tasks close in meaning to `q`. purpose=search powers "Search by meaning" (more, looser
    results); purpose=duplicate powers the "similar task" hint while typing a new title (few,
    very close results only).
    """
    if not await indexing.is_ready(db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search by meaning is not available on this server.",
        )
    search = purpose == "search"
    try:
        results = await similar.find_similar_tasks(
            db,
            client,
            project_id=project_id,
            query=q.strip(),
            min_similarity=(
                similar.SEARCH_MIN_SIMILARITY if search else similar.DUPLICATE_MIN_SIMILARITY
            ),
            limit=8 if search else 3,
            max_gap_from_best=similar.SEARCH_MAX_GAP_FROM_BEST if search else None,
        )
    except AssistantUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return SimilarTasksRead(results=results)
