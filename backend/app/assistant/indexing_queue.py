"""Called by services after a change commits: queues the search-copy update for a worker."""

import logging
import uuid

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return bool(get_settings().assistant_api_key)


def queue_task_indexing(task_id: uuid.UUID) -> None:
    if not _enabled():
        return
    try:
        # Imported here: the worker module pulls in Celery, which plain imports of the
        # services should not need (same pattern as notification_service).
        from app.workers.tasks import index_task_text

        index_task_text.delay(str(task_id))
    except Exception:
        # Never let a queueing problem undo or fail the user's change. The hourly
        # re-index job picks up anything that was not queued.
        logger.exception("Could not queue search indexing for task %s", task_id)


def queue_comment_indexing(comment_id: uuid.UUID) -> None:
    if not _enabled():
        return
    try:
        from app.workers.tasks import index_comment_text

        index_comment_text.delay(str(comment_id))
    except Exception:
        logger.exception("Could not queue search indexing for comment %s", comment_id)
