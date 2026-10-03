"""
Tests for the Phase 3 Stripe payment integration
(app.subscriptions.service.SubscriptionService, stripe_client.StripeClient).

All tests are mock-based: the `stripe` SDK is never actually called (no
network access, no live/test Stripe API key needed) — StripeClient is
patched at the app.subscriptions.service import site, matching this
project's existing test convention of mocking the AsyncSession rather
than hitting a real database or external service.

IMPORTANT — what these tests do NOT prove: they verify this service's
own logic (plan lookup, idempotency bookkeeping, webhook dispatch,
error handling) is correct. They do not, and cannot, prove that a real
Stripe account, real webhook signature, or the actual Checkout/Portal
API behaves as assumed — that requires live (or Stripe CLI test-mode)
credentials this environment does not have. See the final report for
that caveat stated plainly.
"""

import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import stripe

from app.subscriptions.service import SubscriptionService
from app.subscriptions.models import SubscriptionStatus, PlanTier
from app.subscriptions.exceptions import (
    UnknownPlanError,
    SubscriptionNotFoundError,
    InvalidWebhookSignatureError,
)


def _db_execute_mock():
    """db whose execute() returns one plain MagicMock (scalar/scalars are sync)."""
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    return db


def _db_with_sequential(*scalar_values):
    """db.execute() returns each result in order (scalar_one_or_none)."""
    db = AsyncMock()
    results = []
    for value in scalar_values:
        r = MagicMock()
        r.scalar_one_or_none.return_value = value
        results.append(r)
    db.execute.side_effect = results
    return db


def _make_event(event_id: str, event_type: str, data_object: dict) -> dict:
    return {"id": event_id, "type": event_type, "data": {"object": data_object}}


# ═══════════════════════════════════════════════════════════════════
# Checkout Session
# ═══════════════════════════════════════════════════════════════════

class TestCreateCheckoutSession:
    @pytest.mark.asyncio
    async def test_success_returns_stripe_checkout_url(self):
        db = _db_with_sequential(None)  # no existing subscription row
        service = SubscriptionService(db=db)

        with patch("app.subscriptions.service.get_stripe_price_id", return_value="price_123"), \
             patch("app.subscriptions.service.StripeClient") as MockClient:
            MockClient.return_value.create_checkout_session.return_value = MagicMock(
                url="https://checkout.stripe.com/c/session_abc",
            )
            url = await service.create_checkout_session(
                organization_id=uuid.uuid4(),
                plan="starter",
                interval="monthly",
                customer_email="owner@example.com",
            )

        assert url == "https://checkout.stripe.com/c/session_abc"

    @pytest.mark.asyncio
    async def test_unknown_plan_raises_before_calling_stripe(self):
        db = _db_execute_mock()
        service = SubscriptionService(db=db)

        with patch("app.subscriptions.service.get_stripe_price_id", return_value=None), \
             patch("app.subscriptions.service.StripeClient") as MockClient:
            with pytest.raises(UnknownPlanError):
                await service.create_checkout_session(uuid.uuid4(), "not_a_real_plan", "monthly")

            MockClient.assert_not_called()

    @pytest.mark.asyncio
    async def test_reuses_existing_stripe_customer_id(self):
        existing_sub = MagicMock(stripe_customer_id="cus_existing123")
        db = _db_with_sequential(existing_sub)
        service = SubscriptionService(db=db)

        with patch("app.subscriptions.service.get_stripe_price_id", return_value="price_123"), \
             patch("app.subscriptions.service.StripeClient") as MockClient:
            MockClient.return_value.create_checkout_session.return_value = MagicMock(
                url="https://checkout.stripe.com/c/xyz",
            )
            await service.create_checkout_session(uuid.uuid4(), "starter", "monthly")

            _, kwargs = MockClient.return_value.create_checkout_session.call_args
            assert kwargs["customer_id"] == "cus_existing123"


# ═══════════════════════════════════════════════════════════════════
# Billing Portal
# ═══════════════════════════════════════════════════════════════════

class TestBillingPortal:
    @pytest.mark.asyncio
    async def test_no_subscription_raises_not_found(self):
        db = _db_with_sequential(None)
        service = SubscriptionService(db=db)

        with pytest.raises(SubscriptionNotFoundError):
            await service.create_billing_portal_session(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_no_stripe_customer_id_raises_not_found(self):
        sub_without_customer = MagicMock(stripe_customer_id=None)
        db = _db_with_sequential(sub_without_customer)
        service = SubscriptionService(db=db)

        with pytest.raises(SubscriptionNotFoundError):
            await service.create_billing_portal_session(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_success_returns_portal_url(self):
        sub = MagicMock(stripe_customer_id="cus_123")
        db = _db_with_sequential(sub)
        service = SubscriptionService(db=db)

        with patch("app.subscriptions.service.StripeClient") as MockClient:
            MockClient.return_value.create_billing_portal_session.return_value = MagicMock(
                url="https://billing.stripe.com/p/session_xyz",
            )
            url = await service.create_billing_portal_session(uuid.uuid4())

        assert url == "https://billing.stripe.com/p/session_xyz"


# ═══════════════════════════════════════════════════════════════════
# Cancel Subscription
# ═══════════════════════════════════════════════════════════════════

class TestCancelSubscription:
    @pytest.mark.asyncio
    async def test_no_subscription_raises_not_found(self):
        db = _db_with_sequential(None)
        service = SubscriptionService(db=db)

        with pytest.raises(SubscriptionNotFoundError):
            await service.cancel_subscription(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cancel_calls_stripe_at_period_end_and_records_intent(self):
        sub = MagicMock(
            stripe_subscription_id="sub_123",
            status=SubscriptionStatus.ACTIVE,
            canceled_at=None,
        )
        db = _db_with_sequential(sub)
        service = SubscriptionService(db=db)

        with patch("app.subscriptions.service.StripeClient") as MockClient:
            result = await service.cancel_subscription(uuid.uuid4())

        MockClient.return_value.cancel_subscription.assert_called_once_with(
            stripe_subscription_id="sub_123", at_period_end=True,
        )
        assert result.canceled_at is not None
        # Status is intentionally left for the webhook to set — Stripe
        # keeps the subscription active until the period actually ends.
        assert result.status == SubscriptionStatus.ACTIVE
        db.commit.assert_awaited()


# ═══════════════════════════════════════════════════════════════════
# Webhook processing
# ═══════════════════════════════════════════════════════════════════

class TestWebhookSignatureAndIdempotency:
    @pytest.mark.asyncio
    async def test_invalid_signature_raises_domain_error(self):
        db = _db_execute_mock()
        service = SubscriptionService(db=db)

        with patch("app.subscriptions.service.StripeClient") as MockClient:
            MockClient.return_value.construct_webhook_event.side_effect = (
                stripe.SignatureVerificationError("bad signature", "sig_header_value")
            )
            with pytest.raises(InvalidWebhookSignatureError):
                await service.handle_webhook_event(b"payload", "bad-sig")

    @pytest.mark.asyncio
    async def test_duplicate_event_is_recognized_and_skipped(self):
        already_processed = MagicMock()
        db = _db_with_sequential(already_processed)
        service = SubscriptionService(db=db)

        with patch("app.subscriptions.service.StripeClient") as MockClient:
            MockClient.return_value.construct_webhook_event.return_value = _make_event(
                "evt_dup_1", "checkout.session.completed", {},
            )
            result = await service.handle_webhook_event(b"payload", "sig")

        assert result == {
            "received": True, "event_type": "checkout.session.completed", "duplicate": True,
        }
        db.add.assert_not_called()
        db.commit.assert_not_awaited()


class TestWebhookEventHandlers:
    @pytest.mark.asyncio
    async def test_checkout_completed_creates_subscription_row(self):
        # execute #1: dedup check -> not a duplicate
        # execute #2: _get_subscription_row for the org -> none yet
        db = _db_with_sequential(None, None)
        service = SubscriptionService(db=db)

        event = _make_event("evt_1", "checkout.session.completed", {
            "id": "cs_test_1",
            "client_reference_id": str(uuid.uuid4()),
            "customer": "cus_new",
            "subscription": "sub_new",
        })

        with patch("app.subscriptions.service.StripeClient") as MockClient:
            MockClient.return_value.construct_webhook_event.return_value = event
            result = await service.handle_webhook_event(b"payload", "sig")

        assert result["duplicate"] is False
        assert result["event_type"] == "checkout.session.completed"
        # A new Subscription row and a StripeWebhookEvent row were both added.
        assert db.add.call_count == 2
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_checkout_completed_with_no_org_reference_is_a_safe_no_op(self):
        db = _db_with_sequential(None)  # only the dedup check executes
        service = SubscriptionService(db=db)

        event = _make_event("evt_2", "checkout.session.completed", {
            "id": "cs_test_2",
            # no client_reference_id, no metadata.organization_id
        })

        with patch("app.subscriptions.service.StripeClient") as MockClient:
            MockClient.return_value.construct_webhook_event.return_value = event
            result = await service.handle_webhook_event(b"payload", "sig")

        assert result["duplicate"] is False
        # Only the StripeWebhookEvent dedup row was added — no Subscription
        # was fabricated for an unknown organization.
        assert db.add.call_count == 1

    @pytest.mark.asyncio
    async def test_subscription_updated_syncs_plan_status_and_period(self):
        sub = MagicMock(stripe_subscription_id="sub_123")
        db = _db_with_sequential(None, sub)  # dedup check, then lookup by stripe_subscription_id
        service = SubscriptionService(db=db)

        now_ts = int(datetime.now(timezone.utc).timestamp())
        event = _make_event("evt_3", "customer.subscription.updated", {
            "id": "sub_123",
            "status": "active",
            "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
            "current_period_start": now_ts,
            "current_period_end": now_ts + 30 * 86400,
        })

        with patch("app.subscriptions.service.get_plan_for_price_id", return_value="professional"), \
             patch("app.subscriptions.service.StripeClient") as MockClient:
            MockClient.return_value.construct_webhook_event.return_value = event
            result = await service.handle_webhook_event(b"payload", "sig")

        assert result["duplicate"] is False
        assert sub.plan == PlanTier.PROFESSIONAL
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.is_active is True
        assert sub.current_period_end is not None

    @pytest.mark.asyncio
    async def test_subscription_updated_for_unknown_stripe_id_is_a_safe_no_op(self):
        db = _db_with_sequential(None, None)  # dedup check, then lookup finds nothing
        service = SubscriptionService(db=db)

        event = _make_event("evt_4", "customer.subscription.updated", {
            "id": "sub_does_not_exist_locally",
            "status": "active",
        })

        with patch("app.subscriptions.service.StripeClient") as MockClient:
            MockClient.return_value.construct_webhook_event.return_value = event
            result = await service.handle_webhook_event(b"payload", "sig")

        assert result["duplicate"] is False  # event is still recorded as seen
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_subscription_deleted_marks_canceled(self):
        sub = MagicMock(
            stripe_subscription_id="sub_123",
            status=SubscriptionStatus.ACTIVE,
            canceled_at=None,
        )
        db = _db_with_sequential(None, sub)
        service = SubscriptionService(db=db)

        event = _make_event("evt_5", "customer.subscription.deleted", {"id": "sub_123"})

        with patch("app.subscriptions.service.StripeClient") as MockClient:
            MockClient.return_value.construct_webhook_event.return_value = event
            await service.handle_webhook_event(b"payload", "sig")

        assert sub.status == SubscriptionStatus.CANCELED
        assert sub.is_active is False
        assert sub.canceled_at is not None

    @pytest.mark.asyncio
    async def test_payment_failed_marks_past_due(self):
        sub = MagicMock(stripe_subscription_id="sub_123", status=SubscriptionStatus.ACTIVE)
        db = _db_with_sequential(None, sub)
        service = SubscriptionService(db=db)

        event = _make_event("evt_6", "invoice.payment_failed", {"subscription": "sub_123"})

        with patch("app.subscriptions.service.StripeClient") as MockClient:
            MockClient.return_value.construct_webhook_event.return_value = event
            await service.handle_webhook_event(b"payload", "sig")

        assert sub.status == SubscriptionStatus.PAST_DUE

    @pytest.mark.asyncio
    async def test_unhandled_event_type_is_recorded_but_otherwise_a_no_op(self):
        db = _db_with_sequential(None)  # only the dedup check executes
        service = SubscriptionService(db=db)

        event = _make_event("evt_7", "customer.updated", {"id": "cus_123"})

        with patch("app.subscriptions.service.StripeClient") as MockClient:
            MockClient.return_value.construct_webhook_event.return_value = event
            result = await service.handle_webhook_event(b"payload", "sig")

        assert result == {"received": True, "event_type": "customer.updated", "duplicate": False}
        db.commit.assert_awaited()
