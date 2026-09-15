import json
import uuid
from enum import StrEnum
from typing import Any

from redis.asyncio import Redis

_PROJECT_CHANNEL_PREFIX = "project"
_PROJECT_CHANNEL_SUFFIX = "events"
_USER_CHANNEL_PREFIX = "user"
_USER_CHANNEL_SUFFIX = "notifications"


class WSEventType(StrEnum):
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_DELETED = "task_deleted"
    COMMENT_CREATED = "comment_created"
    PRESENCE_JOINED = "presence_joined"
    PRESENCE_LEFT = "presence_left"
    PRESENCE_SNAPSHOT = "presence_snapshot"
    NOTIFICATION = "notification"


def _entity_id_from_channel(channel: str, *, prefix: str, suffix: str) -> uuid.UUID | None:
    parts = channel.split(":")
    if len(parts) != 3 or parts[0] != prefix or parts[2] != suffix:
        return None
    try:
        return uuid.UUID(parts[1])
    except ValueError:
        return None


def channel_name(project_id: uuid.UUID) -> str:
    return f"{_PROJECT_CHANNEL_PREFIX}:{project_id}:{_PROJECT_CHANNEL_SUFFIX}"


def project_id_from_channel(channel: str) -> uuid.UUID | None:
    return _entity_id_from_channel(
        channel, prefix=_PROJECT_CHANNEL_PREFIX, suffix=_PROJECT_CHANNEL_SUFFIX
    )


def notification_channel_name(user_id: uuid.UUID) -> str:
    return f"{_USER_CHANNEL_PREFIX}:{user_id}:{_USER_CHANNEL_SUFFIX}"


def user_id_from_notification_channel(channel: str) -> uuid.UUID | None:
    return _entity_id_from_channel(
        channel, prefix=_USER_CHANNEL_PREFIX, suffix=_USER_CHANNEL_SUFFIX
    )


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


async def publish_notification_event(
    redis: Redis, *, user_id: uuid.UUID, notification: dict[str, Any]
) -> None:
    """
    Same fan-out reasoning as publish_event, but per-user rather than per-project:
    a notification is only ever relevant to its one recipient, so it goes out on
    its own `user:{id}:notifications` channel rather than a project room — a user
    should be notified of a mention even in a project they don't currently have a
    WebSocket room open for.
    """
    payload = {
        "type": WSEventType.NOTIFICATION.value,
        "project_id": None,
        "actor_id": None,
        "data": notification,
    }
    await redis.publish(notification_channel_name(user_id), json.dumps(payload))
