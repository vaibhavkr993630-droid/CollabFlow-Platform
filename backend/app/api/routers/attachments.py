import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_task_project_role
from app.core.redis import get_redis_client
from app.core.storage import generate_presigned_download_url
from app.crud import attachment as attachment_crud
from app.db.session import get_db
from app.models.attachment import Attachment
from app.models.roles import Role
from app.models.task import Task
from app.models.user import User
from app.schemas.attachment import AttachmentDownloadRead, AttachmentRead
from app.services import attachment_service
from app.services.attachment_service import AttachmentServiceError

router = APIRouter(prefix="/api/tasks/{task_id}/attachments", tags=["attachments"])


@router.post("", response_model=AttachmentRead, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    file: UploadFile,
    task: Task = Depends(require_task_project_role(Role.MEMBER)),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
) -> Attachment:
    data = await file.read()
    try:
        return await attachment_service.upload_attachment(
            db,
            redis,
            task_id=task.id,
            project_id=task.project_id,
            uploaded_by_id=current_user.id,
            filename=file.filename or "unnamed",
            content_type=file.content_type or "application/octet-stream",
            data=data,
        )
    except AttachmentServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", response_model=list[AttachmentRead])
async def list_attachments(
    task: Task = Depends(require_task_project_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
) -> list[Attachment]:
    return await attachment_crud.list_by_task(db, task_id=task.id)


@router.get("/{attachment_id}/download", response_model=AttachmentDownloadRead)
async def download_attachment(
    attachment_id: uuid.UUID,
    task: Task = Depends(require_task_project_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
) -> AttachmentDownloadRead:
    attachment = await attachment_crud.get_by_id(db, attachment_id)
    if attachment is None or attachment.task_id != task.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    expires_in = 300
    url = generate_presigned_download_url(
        key=attachment.storage_key, filename=attachment.filename, expires_in=expires_in
    )
    return AttachmentDownloadRead(download_url=url, expires_in=expires_in)


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    attachment_id: uuid.UUID,
    task: Task = Depends(require_task_project_role(Role.ADMIN)),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
) -> None:
    attachment = await attachment_crud.get_by_id(db, attachment_id)
    if attachment is None or attachment.task_id != task.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    await attachment_service.delete_attachment(
        db, redis, attachment=attachment, project_id=task.project_id, actor_id=current_user.id
    )
