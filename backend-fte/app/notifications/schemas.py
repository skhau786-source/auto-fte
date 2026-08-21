import uuid
from datetime import datetime
from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    type: str
    message: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    notifications: list[NotificationOut]
    unread_count: int
