from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    """
    Module-level singleton, not a per-request connection: redis-py's async Redis
    client manages its own internal connection pool, so one client instance shared
    across the process is the intended usage (mirrors how `engine` is a singleton
    in app/db/session.py, with AsyncSessionLocal() making per-request sessions from it).
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def close_redis_client() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
