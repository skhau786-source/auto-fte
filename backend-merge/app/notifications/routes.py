import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RegisteredStudent, Notification
from app.dependencies import get_current_user
from app.notifications.schemas import NotificationOut

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=list[NotificationOut])
async def list_user_notifications(
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification)
        .where(Notification.student_id == current_user.id)
        .order_by(Notification.created_at.desc())
    )
    items = result.scalars().all()
    return [NotificationOut.model_validate(item) for item in items]


@router.patch("/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_as_read(
    notification_id: uuid.UUID,
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Notification).where(
            Notification.id == notification_id, Notification.student_id == current_user.id
        )
    )
    notif = res.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    notif.is_read = True
    await db.commit()
    await db.refresh(notif)
    return NotificationOut.model_validate(notif)
