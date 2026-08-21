import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class GeneratePostRequest(BaseModel):
    prompt: str
    image_model: str = "sdxl"
    aspect_ratio: str = Field(default="1:1", description="1:1 (square), 9:16 (story), 4:5 (portrait)")


class GeneratedPostOut(BaseModel):
    id: uuid.UUID
    prompt: str
    caption: str | None
    image_url: str | None   # full URL frontend can use directly in <img src>
    image_model: str | None
    aspect_ratio: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True