"""Subscription service — manages Stripe billing, plan enforcement, and usage limits."""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.subscriptions.models import (
    Subscription, UsageRecord, PlanTier, SubscriptionStatus,
    get_plan_limits,
)

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Manages subscriptions, billing, and plan enforcement."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_organization_subscription(self, organization_id) -> Optional[Subscription]:
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.organization_id == organization_id,
                Subscription.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def check_plan_limit(
        self, organization_id, limit_key: str, current_value: int
    ) -> tuple[bool, int]:
        """Check if the organization has exceeded a plan limit. Returns (allowed, limit)."""
        sub = await self.get_organization_subscription(organization_id)
        plan = sub.plan.value if sub else PlanTier.FREE.value
        limits = get_plan_limits(plan)
        limit = limits.get(limit_key, 0)
        return current_value < limit, limit

    async def record_api_usage(
        self, organization_id, endpoint: str, method: str,
        status_code: int, duration_ms: int,
    ) -> None:
        record = UsageRecord(
            organization_id=organization_id,
            endpoint=endpoint, method=method,
            status_code=status_code, duration_ms=duration_ms,
        )
        self.db.add(record)
        await self.db.commit()
