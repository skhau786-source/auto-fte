import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class InstagramAccountOut(BaseModel):
    id: uuid.UUID
    ig_user_id: str
    ig_username: str
    account_type: str | None
    connected_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InstagramConnectResponse(BaseModel):
    message: str
    account: InstagramAccountOut


class PublishPostRequest(BaseModel):
    post_id: uuid.UUID


class PublishPostResponse(BaseModel):
    message: str
    instagram_media_id: str
    post_id: uuid.UUID
