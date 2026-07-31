import uuid
from datetime import datetime
from pydantic import BaseModel


class GeneratePostRequest(BaseModel):
    prompt: str
    image_model: str = "sdxl"


class GeneratedPostOut(BaseModel):
    id: uuid.UUID
    prompt: str
    caption: str | None
    image_url: str | None   # full URL frontend can use directly in <img src>
    image_model: str | None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True