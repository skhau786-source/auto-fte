import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class GeneratedPost(Base):
    __tablename__ = "generated_posts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    prompt = Column(Text, nullable=False)
    caption = Column(Text, nullable=True)
    image_path = Column(String(500), nullable=True)
    image_model = Column(String(100), nullable=True)

    status = Column(String(20), default="draft", nullable=False)
    instagram_media_id = Column(String(100), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="generated_posts")
