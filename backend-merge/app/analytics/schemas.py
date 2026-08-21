import uuid
from datetime import datetime
from pydantic import BaseModel


class PostAnalyticsOut(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID
    likes: int
    comments: int
    reach: int
    impressions: int
    fetched_at: datetime

    class Config:
        from_attributes = True


class AnalyticsSummaryOut(BaseModel):
    total_posts: int
    published_posts: int
    total_likes: int
    total_comments: int
    total_reach: int
    total_impressions: int
    latest_analytics: list[PostAnalyticsOut]
