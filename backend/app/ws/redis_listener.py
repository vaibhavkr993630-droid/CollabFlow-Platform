import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


async def run_pattern_listener(
    redis: Redis,
    *,
    pattern: str,
    extract_id: Callable[[str], uuid.UUID | None],
    deliver: Callable[[uuid.UUID, dict], Awaitable[None]],
) -> None:
    """
    Runs for the lifetime of the app (started/cancelled from main.py's lifespan).
    One long-lived pattern subscription rather than opening a subscription per
    active project/user — the same connection handles every project room and,
    separately, every user's notification channel, regardless of how many of
    either currently exist.

    Generic over what's being listened for: main.py starts one instance of this
    for project events (pattern "project:*:events", relaying to ConnectionManager)
    and a second for notifications (pattern "user:*:notifications", relaying to
    NotificationConnectionManager) — same delivery mechanism, different channel
    namespace and manager.
    """
    pubsub = redis.pubsub()
    await pubsub.psubscribe(pattern)
    logger.info("Redis listener subscribed to %s", pattern)

    try:
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue

            entity_id = extract_id(message["channel"])
            if entity_id is None:
                logger.warning("Unrecognized pub/sub channel: %s", message["channel"])
                continue

            try:
                payload = json.loads(message["data"])
            except json.JSONDecodeError:
                logger.warning("Malformed event payload on %s", message["channel"])
                continue

            await deliver(entity_id, payload)
    except asyncio.CancelledError:
        await pubsub.punsubscribe(pattern)
        await pubsub.aclose()
        raise
