import json
import uuid
from enum import StrEnum
from typing import Any

from redis.asyncio import Redis

_CHANNEL_PREFIX = "project"
_CHANNEL_SUFFIX = "events"


class WSEventType(StrEnum):
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_DELETED = "task_deleted"
    COMMENT_CREATED = "comment_created"
    PRESENCE_JOINED = "presence_joined"
    PRESENCE_LEFT = "presence_left"
    PRESENCE_SNAPSHOT = "presence_snapshot"


def channel_name(project_id: uuid.UUID) -> str:
    return f"{_CHANNEL_PREFIX}:{project_id}:{_CHANNEL_SUFFIX}"


def project_id_from_channel(channel: str) -> uuid.UUID | None:
    parts = channel.split(":")
    if len(parts) != 3 or parts[0] != _CHANNEL_PREFIX or parts[2] != _CHANNEL_SUFFIX:
        return None
    try:
        return uuid.UUID(parts[1])
    except ValueError:
        return None


async def publish_event(
    redis: Redis,
    *,
    project_id: uuid.UUID,
    event_type: WSEventType,
    data: dict[str, Any],
    actor_id: uuid.UUID | None = None,
) -> None:
    """
    Publishes to Redis rather than pushing straight to local WebSocket connections.
    Every backend instance (including this one) subscribes to the same channel and
    relays to whichever clients happen to be connected to *it* — this is what lets
    the design scale horizontally: a task updated via an API call served by instance
    A still reaches a WebSocket client connected to instance B. Only one instance
    runs in this project's demo deployment, but the flow through Redis is identical
    either way — see README for the tradeoff this is deliberately paying for.
    """
    payload = {
        "type": event_type.value,
        "project_id": str(project_id),
        "actor_id": str(actor_id) if actor_id else None,
        "data": data,
    }
    await redis.publish(channel_name(project_id), json.dumps(payload))
