import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class BrandProfileCreate(BaseModel):
    tone: str = Field(default="professional", description="e.g. professional, playful, luxury, witty")
    sample_captions: str | None = Field(default=None, description="Examples of brand style captions")
    prohibited_words: str | None = Field(default=None, description="Words/phrases to never use")
    emoji_preference: str = Field(default="moderate", description="e.g. none, minimal, moderate, heavy")
    target_audience: str | None = Field(default=None, description="Description of target audience")


class BrandProfileUpdate(BaseModel):
    tone: str | None = None
    sample_captions: str | None = None
    prohibited_words: str | None = None
    emoji_preference: str | None = None
    target_audience: str | None = None


class BrandProfileOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    tone: str
    sample_captions: str | None
    prohibited_words: str | None
    emoji_preference: str
    target_audience: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
