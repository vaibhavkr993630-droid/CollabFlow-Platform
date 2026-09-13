import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import activity as activity_crud
from app.models.activity import ActivityAction, ActivityLog


async def log(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: ActivityAction,
    summary: str,
    task_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> ActivityLog:
    """
    Records one activity entry. Callers add this to the same unit of work as the
    triggering change (flush only, no commit) so the log entry only persists if the
    action it describes actually commits — an activity log entry for a task that
    failed to save would be worse than no entry at all.
    """
    return await activity_crud.create(
        db,
        project_id=project_id,
        actor_id=actor_id,
        action=action,
        summary=summary,
        task_id=task_id,
        metadata=metadata,
    )
