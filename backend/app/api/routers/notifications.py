import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.crud import notification as notification_crud
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import (
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationRead,
    UnreadCountResponse,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationListResponse:
    items, total = await notification_crud.list_by_user(
        db, user_id=current_user.id, page=page, page_size=page_size
    )
    return NotificationListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UnreadCountResponse:
    count = await notification_crud.unread_count(db, user_id=current_user.id)
    return UnreadCountResponse(unread_count=count)


@router.post("/read-all", response_model=MarkAllReadResponse)
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarkAllReadResponse:
    count = await notification_crud.mark_all_read(db, user_id=current_user.id)
    await db.commit()
    return MarkAllReadResponse(marked_read=count)


@router.post("/{notification_id}/read", response_model=NotificationRead)
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Notification:
    notification = await notification_crud.get_by_id(db, notification_id)
    if notification is None or notification.user_id != current_user.id:
        # 404, not 403: don't reveal that a notification with this id exists but
        # belongs to someone else.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    notification = await notification_crud.mark_read(db, notification)
    await db.commit()
    await db.refresh(notification)
    return notification
