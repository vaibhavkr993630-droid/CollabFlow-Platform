"""FastAPI dependencies shared by every assistant endpoint."""

from datetime import UTC, datetime

from fastapi import Depends, HTTPException, status
from redis.asyncio import Redis

from app.assistant.client import AssistantClient, ChatCompletionsClient
from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.redis import get_redis_client
from app.models.user import User

_SECONDS_IN_TWO_DAYS = 2 * 24 * 60 * 60


def get_assistant_client() -> AssistantClient | None:
    """The configured client, or None when no key is set (assistant features are off)."""
    settings = get_settings()
    if not settings.assistant_api_key:
        return None
    return ChatCompletionsClient(
        base_url=settings.assistant_base_url,
        api_key=settings.assistant_api_key,
        model=settings.assistant_model,
        timeout_seconds=settings.assistant_timeout_seconds,
        reasoning_effort=settings.assistant_reasoning_effort or None,
    )


def require_assistant(
    client: AssistantClient | None = Depends(get_assistant_client),
) -> AssistantClient:
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Assistant features are turned off on this server.",
        )
    return client


async def enforce_daily_limit(
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis_client),
) -> User:
    """
    Counts one assistant request for this user today (UTC) and refuses past the limit.
    A Redis counter per user per day: INCR is atomic, so parallel requests cannot slip
    past the limit, and the key expires on its own. Every attempt counts, including
    ones the provider later fails, which keeps the check simple and the quota safe.
    """
    limit = get_settings().assistant_daily_limit
    key = f"assistant:usage:{current_user.id}:{datetime.now(UTC).date().isoformat()}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, _SECONDS_IN_TWO_DAYS)
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You've reached today's limit of {limit} assistant requests. "
            "It resets at midnight UTC.",
        )
    return current_user
