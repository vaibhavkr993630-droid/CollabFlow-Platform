import uuid

from redis.asyncio import Redis


def _presence_key(project_id: uuid.UUID) -> str:
    return f"presence:{project_id}"


async def join(redis: Redis, *, project_id: uuid.UUID, user_id: uuid.UUID) -> int:
    """
    Increments this user's connection count for the project (a Redis hash of
    user_id -> open-connection-count, not a plain set) and returns the new count.
    A ref count, not a set, because a user can hold multiple tabs — and possibly
    connections spread across multiple backend instances — open to the same
    project; they're only "offline" once every one of those closes.
    """
    return await redis.hincrby(_presence_key(project_id), str(user_id), 1)


async def leave(redis: Redis, *, project_id: uuid.UUID, user_id: uuid.UUID) -> int:
    key = _presence_key(project_id)
    count = await redis.hincrby(key, str(user_id), -1)
    if count <= 0:
        await redis.hdel(key, str(user_id))
    return count


async def online_user_ids(redis: Redis, *, project_id: uuid.UUID) -> list[str]:
    return list(await redis.hkeys(_presence_key(project_id)))
