"""Subscription & billing models for Stripe integration."""

import os
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

# Stripe Price IDs — read from environment variables, never hard-coded,
# since a real price id is specific to one Stripe account and differs
# between dev/staging/production. Naming convention:
# STRIPE_PRICE_<PLAN>_<INTERVAL>, e.g. STRIPE_PRICE_STARTER_MONTHLY.
# Empty string means "not configured for this deployment" — attempting a
# checkout for such a plan/interval raises UnknownPlanError rather than
# silently sending Stripe an empty price id.
_BILLABLE_PLANS = (PlanTier.STARTER, PlanTier.PROFESSIONAL, PlanTier.ENTERPRISE)
_INTERVALS = ("monthly", "yearly")

STRIPE_PRICE_IDS: dict[str, str] = {
    f"{plan.value}_{interval}": os.environ.get(
        f"STRIPE_PRICE_{plan.value.upper()}_{interval.upper()}", ""
    )
    for plan in _BILLABLE_PLANS
    for interval in _INTERVALS
}


def get_stripe_price_id(plan: str, interval: str) -> Optional[str]:
    """Look up the configured Stripe price id for a plan/interval, or None."""
    price_id = STRIPE_PRICE_IDS.get(f"{plan}_{interval}", "")
    return price_id or None


def get_plan_for_price_id(price_id: str) -> Optional[str]:
    """Reverse lookup: which plan tier does this Stripe price id belong to?"""
    for key, configured_price_id in STRIPE_PRICE_IDS.items():
        if configured_price_id and configured_price_id == price_id:
            return key.rsplit("_", 1)[0]
    return None


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
        Enum(PlanTier, name="plan_tier_enum", values_callable=lambda e: [m.value for m in e]),
        default=PlanTier.FREE,
        nullable=False,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status_enum", values_callable=lambda e: [m.value for m in e]),
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


class StripeWebhookEvent(Base):
    """
    Records every Stripe webhook event this app has already processed.

    Stripe explicitly does not guarantee at-most-once delivery — the same
    event can be (and in production regularly is) delivered more than
    once. The event's own `id` (e.g. "evt_...") is globally unique per
    Stripe account, so recording it here before acting on it turns
    webhook processing into an idempotent operation: a duplicate delivery
    is recognized and skipped instead of being applied twice (e.g.
    double-activating a subscription).
    """
    __tablename__ = "stripe_webhook_events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
