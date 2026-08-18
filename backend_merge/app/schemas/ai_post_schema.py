import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class GeneratePostRequest(BaseModel):
    prompt: str
    image_model: str = "sdxl"


class GeneratedPostOut(BaseModel):
    id: uuid.UUID
    prompt: str
    caption: str | None
    image_url: str | None
    image_model: str | None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
