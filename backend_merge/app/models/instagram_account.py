import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class InstagramAccount(Base):
    """Stores connected Instagram Business/Creator Account per user."""

    __tablename__ = "instagram_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    ig_user_id = Column(String(100), nullable=False)
    ig_username = Column(String(150), nullable=False)
    account_type = Column(String(50), nullable=True)
    facebook_page_id = Column(String(100), nullable=True)

    access_token = Column(Text, nullable=False)
    token_expires_at = Column(DateTime(timezone=True), nullable=False)

    connected_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="instagram_account")
