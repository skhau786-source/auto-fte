import uuid
from datetime import datetime
from pydantic import BaseModel


class CommentOut(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID
    comment_id: str
    commenter_username: str
    comment_text: str
    ai_reply: str | None
    status: str
    replied_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class ManualReplyRequest(BaseModel):
    comment_id: str
    custom_reply: str | None = None
