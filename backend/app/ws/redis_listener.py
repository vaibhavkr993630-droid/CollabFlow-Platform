import asyncio
import json
import logging

from redis.asyncio import Redis

from app.ws.connection_manager import ConnectionManager
from app.ws.events import project_id_from_channel

logger = logging.getLogger(__name__)

_PATTERN = "project:*:events"


async def run_redis_listener(redis: Redis, manager: ConnectionManager) -> None:
    """
    Runs for the lifetime of the app (started/cancelled from main.py's lifespan).
    Pattern-subscribes once to every project's channel rather than opening a
    subscription per active project — one long-lived Redis connection regardless
    of how many project rooms exist, versus needing to open/close a subscription
    every time a project's first/last WebSocket client connects/disconnects.
    """
    pubsub = redis.pubsub()
    await pubsub.psubscribe(_PATTERN)
    logger.info("Redis listener subscribed to %s", _PATTERN)

    try:
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue

            project_id = project_id_from_channel(message["channel"])
            if project_id is None:
                logger.warning("Unrecognized pub/sub channel: %s", message["channel"])
                continue

            try:
                payload = json.loads(message["data"])
            except json.JSONDecodeError:
                logger.warning("Malformed event payload on %s", message["channel"])
                continue

            await manager.send_to_project(project_id, payload)
    except asyncio.CancelledError:
        await pubsub.punsubscribe(_PATTERN)
        await pubsub.aclose()
        raise
