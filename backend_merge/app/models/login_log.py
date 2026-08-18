import enum

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class LoginMethod(str, enum.Enum):
    LOCAL = "local"
    GOOGLE = "google"


class LoginLog(Base):
    """Har login ka audit record - team member ke login_users table ka local version."""

    __tablename__ = "login_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    login_method = Column(String(20), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    logged_in_at = Column(DateTime(timezone=True), server_default=func.now())
