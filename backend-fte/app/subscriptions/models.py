"""Subscription & billing models for Stripe integration."""

import uuid
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum, func, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PlanTier(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    TRIALING = "trialing"
    PAUSED = "paused"


# ═══════════════════════════════════════════════════════════════════
# PLAN DEFINITIONS
# ═══════════════════════════════════════════════════════════════════

PLAN_LIMITS: dict[str, dict] = {
    PlanTier.FREE.value: {
        "max_products": 50,
        "max_variants": 200,
        "max_users": 2,
        "max_stores": 1,
        "max_api_requests_per_hour": 100,
        "max_storage_mb": 50,
        "max_webhooks": 3,
        "scheduler_enabled": False,
        "export_enabled": True,
        "dashboard_enabled": True,
        "admin_apis_enabled": False,
        "audit_retention_days": 7,
    },
    PlanTier.STARTER.value: {
        "max_products": 500,
        "max_variants": 2000,
        "max_users": 5,
        "max_stores": 1,
        "max_api_requests_per_hour": 1000,
        "max_storage_mb": 500,
        "max_webhooks": 10,
        "scheduler_enabled": True,
        "export_enabled": True,
        "dashboard_enabled": True,
        "admin_apis_enabled": False,
        "audit_retention_days": 30,
    },
    PlanTier.PROFESSIONAL.value: {
        "max_products": 5000,
        "max_variants": 25000,
        "max_users": 20,
        "max_stores": 3,
        "max_api_requests_per_hour": 5000,
        "max_storage_mb": 2000,
        "max_webhooks": 25,
        "scheduler_enabled": True,
        "export_enabled": True,
        "dashboard_enabled": True,
        "admin_apis_enabled": True,
        "audit_retention_days": 90,
    },
    PlanTier.ENTERPRISE.value: {
        "max_products": 100000,
        "max_variants": 500000,
        "max_users": 999,
        "max_stores": 50,
        "max_api_requests_per_hour": 50000,
        "max_storage_mb": 10000,
        "max_webhooks": 100,
        "scheduler_enabled": True,
        "export_enabled": True,
        "dashboard_enabled": True,
        "admin_apis_enabled": True,
        "audit_retention_days": 365,
    },
}

# Stripe Price IDs (set per environment)
STRIPE_PRICE_IDS: dict[str, str] = {
    # Format: "plan_interval" -> "price_id"
    # These should be set in environment variables
    PlanTier.STARTER.value + "_monthly": "",
    PlanTier.STARTER.value + "_yearly": "",
    PlanTier.PROFESSIONAL.value + "_monthly": "",
    PlanTier.PROFESSIONAL.value + "_yearly": "",
    PlanTier.ENTERPRISE.value + "_monthly": "",
    PlanTier.ENTERPRISE.value + "_yearly": "",
}


def get_plan_limits(plan: str) -> dict:
    """Get the feature limits for a given plan tier."""
    return PLAN_LIMITS.get(plan, PLAN_LIMITS[PlanTier.FREE.value])


# ═══════════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════════


class Subscription(Base):
    """Tracks organization subscriptions and Stripe billing."""
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    plan: Mapped[PlanTier] = mapped_column(
        Enum(PlanTier, name="plan_tier_enum"),
        default=PlanTier.FREE,
        nullable=False,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status_enum"),
        default=SubscriptionStatus.ACTIVE,
        nullable=False,
    )

    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    stripe_price_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    current_period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Usage tracking
    total_api_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_storage_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    organization: Mapped["Organization"] = relationship()


class UsageRecord(Base):
    """Tracks API usage per organization for rate limiting and billing."""
    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
