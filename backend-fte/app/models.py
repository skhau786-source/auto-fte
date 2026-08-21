import uuid
import enum
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum, func, Text, Integer
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
    brand_profile: Mapped["BrandProfile | None"] = relationship(
        back_populates="student", uselist=False, cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    scheduled_posts: Mapped[list["ScheduledPost"]] = relationship(
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
    aspect_ratio: Mapped[str] = mapped_column(String(20), server_default="1:1", nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    instagram_media_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    comments: Mapped[list["PostComment"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )
    analytics: Mapped[list["PostAnalytics"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )
    scheduled_item: Mapped["ScheduledPost | None"] = relationship(
        back_populates="post", uselist=False, cascade="all, delete-orphan"
    )


class InstagramAccount(Base):
    """Stores the connected Instagram Business Account per user."""
    __tablename__ = "instagram_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("registered_students.id", ondelete="CASCADE"), nullable=False, index=True
    )

    ig_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    ig_username: Mapped[str] = mapped_column(String(150), nullable=False)
    account_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    facebook_page_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BrandProfile(Base):
    __tablename__ = "brand_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    tone: Mapped[str] = mapped_column(String(100), default="professional", nullable=False)
    sample_captions: Mapped[str | None] = mapped_column(Text, nullable=True)
    prohibited_words: Mapped[str | None] = mapped_column(Text, nullable=True)
    emoji_preference: Mapped[str] = mapped_column(String(50), default="moderate", nullable=False)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    student: Mapped["RegisteredStudent"] = relationship(back_populates="brand_profile")


class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_posts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    scheduled_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    post: Mapped["GeneratedPost"] = relationship(back_populates="scheduled_item")
    student: Mapped["RegisteredStudent"] = relationship(back_populates="scheduled_posts")


class PostComment(Base):
    __tablename__ = "post_comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    comment_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    commenter_username: Mapped[str] = mapped_column(String(150), nullable=False)
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    ai_reply: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    post: Mapped["GeneratedPost"] = relationship(back_populates="comments")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student: Mapped["RegisteredStudent"] = relationship(back_populates="notifications")


class PostAnalytics(Base):
    __tablename__ = "post_analytics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    likes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reach: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    post: Mapped["GeneratedPost"] = relationship(back_populates="analytics")