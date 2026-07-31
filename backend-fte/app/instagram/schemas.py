import uuid
from datetime import datetime
from pydantic import BaseModel


class InstagramAccountOut(BaseModel):
    id: uuid.UUID
    ig_user_id: str
    ig_username: str
    account_type: str | None
    connected_at: datetime

    class Config:
        from_attributes = True


class InstagramConnectResponse(BaseModel):
    message: str
    account: InstagramAccountOut