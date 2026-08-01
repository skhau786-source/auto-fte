import uuid
import enum
from datetime import datetime
from sqlalchemy import Text

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum, func
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AuthProvider(str, enum.Enum):
    LOCAL = "local"
    GOOGLE = "google"


class LoginMethod(str, enum.Enum):
    LOCAL = "local"
    GOOGLE = "google"


class RegisteredStudent(Base):
    __tablename__ = "registered_students"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(150), nullable=True)

    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    auth_provider: Mapped[AuthProvider] = mapped_column(
        Enum(AuthProvider, name="auth_provider_enum"), default=AuthProvider.LOCAL, nullable=False
    )
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    login_records: Mapped[list["LoginUser"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )


class LoginUser(Base):
    __tablename__ = "login_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    login_method: Mapped[LoginMethod] = mapped_column(Enum(LoginMethod, name="login_method_enum"), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # ✅ ADD THIS LINE
    session_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    logged_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student: Mapped["RegisteredStudent"] = relationship(back_populates="login_records")


class GeneratedPost(Base):
    __tablename__ = "generated_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("registered_students.id", ondelete="CASCADE"), nullable=False, index=True
    )

    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    instagram_media_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # NEW
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # NEW

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    
# --- agar Text import nahi hai to top pe add karo ---
from sqlalchemy import Text

# --- ye class models.py ke end me append karo ---

class InstagramAccount(Base):
    """Stores the connected Instagram Business Account per user."""
    __tablename__ = "instagram_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("registered_students.id", ondelete="CASCADE"), nullable=False, index=True
    )

    ig_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    ig_username: Mapped[str] = mapped_column(String(150), nullable=False)
    account_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # BUSINESS / MEDIA_CREATOR
    facebook_page_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # no longer required in new flow

    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())