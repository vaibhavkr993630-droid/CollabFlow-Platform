from fastapi import APIRouter, Depends

from app.assistant.client import AssistantClient
from app.assistant.deps import get_assistant_client

router = APIRouter(prefix="/api/features", tags=["features"])


@router.get("")
async def list_features(
    client: AssistantClient | None = Depends(get_assistant_client),
) -> dict[str, bool]:
    """Which optional features this server has switched on, so the UI can hide the rest."""
    return {"assistant": client is not None}
