import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class SchedulePostCreate(BaseModel):
    post_id: uuid.UUID
    scheduled_time: datetime = Field(description="ISO 8601 UTC datetime for post publishing")
    public_image_url: str | None = Field(default=None, description="Optional public ngrok image URL")


class SchedulePostOut(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID
    student_id: uuid.UUID
    scheduled_time: datetime
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
