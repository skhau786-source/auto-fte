"""Subscription service — manages Stripe billing, plan enforcement, and usage limits."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import stripe
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.subscriptions.models import (
    Subscription, UsageRecord, StripeWebhookEvent, PlanTier, SubscriptionStatus,
    get_plan_limits, get_stripe_price_id, get_plan_for_price_id,
)
from app.subscriptions.stripe_client import StripeClient
from app.subscriptions.exceptions import (
    UnknownPlanError,
    SubscriptionNotFoundError,
    InvalidWebhookSignatureError,
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

    # ═══════════════════════════════════════════════════════════════
    # CHECKOUT / BILLING PORTAL
    # ═══════════════════════════════════════════════════════════════

    async def create_checkout_session(
        self,
        organization_id: uuid.UUID,
        plan: str,
        interval: str = "monthly",
        customer_email: Optional[str] = None,
    ) -> str:
        """Create a Stripe Checkout Session URL for upgrading to `plan`/`interval`."""
        price_id = get_stripe_price_id(plan, interval)
        if not price_id:
            raise UnknownPlanError(plan, interval)

        existing = await self._get_subscription_row(organization_id)
        customer_id = existing.stripe_customer_id if existing else None

        client = StripeClient()
        session = client.create_checkout_session(
            price_id=price_id,
            customer_id=customer_id,
            customer_email=customer_email,
            organization_id=str(organization_id),
        )
        return session.url

    async def create_billing_portal_session(self, organization_id: uuid.UUID) -> str:
        """Create a Stripe Billing Portal URL so the customer can self-manage billing."""
        sub = await self._get_subscription_row(organization_id)
        if sub is None or not sub.stripe_customer_id:
            raise SubscriptionNotFoundError(organization_id)

        client = StripeClient()
        session = client.create_billing_portal_session(customer_id=sub.stripe_customer_id)
        return session.url

    async def cancel_subscription(self, organization_id: uuid.UUID) -> Subscription:
        """
        Cancel an organization's subscription at the end of the current
        billing period (not immediately — the customer keeps access they
        already paid for).

        `status` is intentionally left untouched here: Stripe keeps the
        subscription "active" (with cancel_at_period_end=true) until the
        period actually ends, at which point it sends
        customer.subscription.updated/deleted — that webhook is what
        actually flips `status` to CANCELED. Only `canceled_at` (the
        cancellation *request* time) is recorded immediately, matching
        what the API can honestly assert.
        """
        sub = await self._get_subscription_row(organization_id)
        if sub is None or not sub.stripe_subscription_id:
            raise SubscriptionNotFoundError(organization_id)

        client = StripeClient()
        client.cancel_subscription(
            stripe_subscription_id=sub.stripe_subscription_id, at_period_end=True,
        )

        sub.canceled_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    # ═══════════════════════════════════════════════════════════════
    # WEBHOOK PROCESSING
    # ═══════════════════════════════════════════════════════════════

    async def handle_webhook_event(self, payload: bytes, sig_header: str) -> dict:
        """
        Verify, deduplicate, and apply one Stripe webhook event.

        Idempotent: the event's own id is recorded in stripe_webhook_events
        (primary key) before it's acted on. Stripe explicitly does not
        guarantee at-most-once delivery, so a redelivered event is
        recognized here and skipped rather than reapplied (which would,
        e.g., double-process a completed checkout).
        """
        client = StripeClient()
        try:
            event = client.construct_webhook_event(payload, sig_header)
        except stripe.SignatureVerificationError as exc:
            raise InvalidWebhookSignatureError() from exc

        event_id = event["id"]
        event_type = event["type"]

        result = await self.db.execute(
            select(StripeWebhookEvent).where(StripeWebhookEvent.id == event_id)
        )
        if result.scalar_one_or_none() is not None:
            logger.info(
                "Duplicate Stripe webhook event %s (%s) — already processed, skipping",
                event_id, event_type,
            )
            return {"received": True, "event_type": event_type, "duplicate": True}

        self.db.add(StripeWebhookEvent(id=event_id, event_type=event_type))

        data_object = event["data"]["object"]

        if event_type == "checkout.session.completed":
            await self._handle_checkout_completed(data_object)
        elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
            await self._handle_subscription_updated(data_object)
        elif event_type == "customer.subscription.deleted":
            await self._handle_subscription_deleted(data_object)
        elif event_type == "invoice.payment_failed":
            await self._handle_payment_failed(data_object)
        else:
            logger.info("Unhandled Stripe event type (recorded, no-op): %s", event_type)

        await self.db.commit()
        return {"received": True, "event_type": event_type, "duplicate": False}

    async def _get_subscription_row(self, organization_id: uuid.UUID) -> Optional[Subscription]:
        result = await self.db.execute(
            select(Subscription).where(Subscription.organization_id == organization_id)
        )
        return result.scalar_one_or_none()

    async def _get_or_create_subscription_row(self, organization_id) -> Subscription:
        sub = await self._get_subscription_row(organization_id)
        if sub is None:
            sub = Subscription(organization_id=organization_id)
            self.db.add(sub)
            await self.db.flush()
        return sub

    async def _handle_checkout_completed(self, session_obj: dict) -> None:
        organization_id = session_obj.get("client_reference_id") or (
            session_obj.get("metadata") or {}
        ).get("organization_id")
        if not organization_id:
            logger.error(
                "checkout.session.completed with no organization reference: session=%s",
                session_obj.get("id"),
            )
            return

        sub = await self._get_or_create_subscription_row(organization_id)
        if session_obj.get("customer"):
            sub.stripe_customer_id = session_obj["customer"]
        if session_obj.get("subscription"):
            sub.stripe_subscription_id = session_obj["subscription"]
        sub.is_active = True
        # Plan/status/period fields come from the customer.subscription.*
        # webhook Stripe sends alongside this one — not duplicated here.

    async def _handle_subscription_updated(self, sub_obj: dict) -> None:
        stripe_subscription_id = sub_obj.get("id")
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id,
            )
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            logger.warning(
                "customer.subscription.updated for unknown stripe_subscription_id=%s",
                stripe_subscription_id,
            )
            return

        items = (sub_obj.get("items") or {}).get("data") or []
        price_id = items[0]["price"]["id"] if items and items[0].get("price") else None
        plan_key = get_plan_for_price_id(price_id) if price_id else None
        if plan_key:
            sub.plan = PlanTier(plan_key)
            sub.stripe_price_id = price_id

        status_value = sub_obj.get("status")
        try:
            if status_value:
                sub.status = SubscriptionStatus(status_value)
        except ValueError:
            logger.warning("Unknown Stripe subscription status: %s", status_value)

        if sub_obj.get("current_period_start"):
            sub.current_period_start = datetime.fromtimestamp(
                sub_obj["current_period_start"], tz=timezone.utc,
            )
        if sub_obj.get("current_period_end"):
            sub.current_period_end = datetime.fromtimestamp(
                sub_obj["current_period_end"], tz=timezone.utc,
            )
        if sub_obj.get("trial_end"):
            sub.trial_end = datetime.fromtimestamp(sub_obj["trial_end"], tz=timezone.utc)

        sub.is_active = status_value in ("active", "trialing")

    async def _handle_subscription_deleted(self, sub_obj: dict) -> None:
        stripe_subscription_id = sub_obj.get("id")
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id,
            )
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            return
        sub.status = SubscriptionStatus.CANCELED
        sub.is_active = False
        sub.canceled_at = sub.canceled_at or datetime.now(timezone.utc)

    async def _handle_payment_failed(self, invoice_obj: dict) -> None:
        stripe_subscription_id = invoice_obj.get("subscription")
        if not stripe_subscription_id:
            return
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id,
            )
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            return
        sub.status = SubscriptionStatus.PAST_DUE
