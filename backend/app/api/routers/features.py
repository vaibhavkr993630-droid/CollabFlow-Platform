from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import indexing
from app.assistant.client import AssistantClient
from app.assistant.deps import get_assistant_client
from app.db.session import get_db

router = APIRouter(prefix="/api/features", tags=["features"])


@router.get("")
async def list_features(
    client: AssistantClient | None = Depends(get_assistant_client),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Which optional features this server has switched on, so the UI can hide the rest."""
    assistant = client is not None
    return {
        "assistant": assistant,
        # Needs the pgvector table too, which databases without the extension do not have.
        "smart_search": assistant and await indexing.is_ready(db),
    }
