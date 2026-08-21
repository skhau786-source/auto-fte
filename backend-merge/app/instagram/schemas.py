import uuid
from datetime import datetime
from pydantic import BaseModel


class InstagramAccountOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    ig_user_id: str
    ig_username: str
    account_type: str | None
    facebook_page_id: str | None
    token_expires_at: datetime
    connected_at: datetime

    class Config:
        from_attributes = True


class InstagramPublishRequest(BaseModel):
    post_id: uuid.UUID
    public_image_url: str
