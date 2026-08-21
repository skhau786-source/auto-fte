import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class PostGenerateRequest(BaseModel):
    prompt: str = Field(min_length=3, description="Topic or prompt for image & caption generation")
    model: str = Field(default="sdxl", description="Image model: sdxl or flux")
    aspect_ratio: str = Field(default="1:1", description="1:1 (feed) or 9:16 (story) or 4:5")
    style_preset: str | None = Field(default=None, description="e.g. minimalist, vintage, vibrant, cinematic")


class PostOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    prompt: str
    caption: str | None
    image_path: str | None
    image_model: str | None
    aspect_ratio: str
    status: str
    instagram_media_id: str | None
    published_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class PostGenerateResponse(BaseModel):
    message: str
    post: PostOut
