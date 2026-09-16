import uuid

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.storage import build_storage_key, delete_object, upload_bytes
from app.crud import attachment as attachment_crud
from app.models.activity import ActivityAction
from app.models.attachment import Attachment
from app.services import activity_service
from app.ws.events import WSEventType, publish_event

settings = get_settings()


class AttachmentServiceError(Exception):
    """Raised for validation failures — mapped to 4xx at the router."""


def _validate(*, filename: str, size_bytes: int) -> None:
    if size_bytes == 0:
        raise AttachmentServiceError("File is empty")

    max_bytes = settings.max_attachment_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise AttachmentServiceError(
            f"File exceeds the {settings.max_attachment_size_mb}MB attachment size limit"
        )

    if not filename.strip():
        raise AttachmentServiceError("Filename is required")


async def upload_attachment(
    db: AsyncSession,
    redis: Redis,
    *,
    task_id: uuid.UUID,
    project_id: uuid.UUID,
    uploaded_by_id: uuid.UUID,
    filename: str,
    content_type: str,
    data: bytes,
) -> Attachment:
    _validate(filename=filename, size_bytes=len(data))

    storage_key = build_storage_key(task_id, filename)
    # Upload to MinIO before writing the DB row: if the upload fails, there's
    # nothing to roll back. Writing the row first and having the upload fail
    # after would leave a database record pointing at a file that doesn't exist.
    upload_bytes(key=storage_key, data=data, content_type=content_type)

    attachment = await attachment_crud.create(
        db,
        task_id=task_id,
        uploaded_by_id=uploaded_by_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        storage_key=storage_key,
    )
    await activity_service.log(
        db,
        project_id=project_id,
        task_id=task_id,
        actor_id=uploaded_by_id,
        action=ActivityAction.ATTACHMENT_ADDED,
        summary=f"attached '{filename}'",
    )
    await db.commit()
    await db.refresh(attachment)

    await publish_event(
        redis,
        project_id=project_id,
        event_type=WSEventType.ATTACHMENT_ADDED,
        data={
            "id": str(attachment.id),
            "task_id": str(task_id),
            "filename": filename,
            "size_bytes": attachment.size_bytes,
        },
        actor_id=uploaded_by_id,
    )
    return attachment


async def delete_attachment(
    db: AsyncSession,
    redis: Redis,
    *,
    attachment: Attachment,
    project_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    attachment_id, task_id, filename, storage_key = (
        attachment.id,
        attachment.task_id,
        attachment.filename,
        attachment.storage_key,
    )

    await activity_service.log(
        db,
        project_id=project_id,
        task_id=task_id,
        actor_id=actor_id,
        action=ActivityAction.ATTACHMENT_REMOVED,
        summary=f"removed attachment '{filename}'",
    )
    await attachment_crud.delete(db, attachment)
    await db.commit()

    # Object deletion after the DB commit, not before: if MinIO is unreachable,
    # the metadata row is already gone either way, so there's no partial-state
    # inconsistency worth blocking the request over — worth revisiting if orphaned
    # objects in the bucket ever become a real operational problem at this scale.
    delete_object(key=storage_key)

    await publish_event(
        redis,
        project_id=project_id,
        event_type=WSEventType.ATTACHMENT_REMOVED,
        data={"id": str(attachment_id), "task_id": str(task_id), "filename": filename},
        actor_id=actor_id,
    )
