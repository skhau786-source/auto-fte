"""
Thin wrapper around the `stripe` SDK.

Isolating every direct `stripe.*` call behind this class keeps
SubscriptionService testable without a live Stripe account or network
access: tests mock `StripeClient`, not the third-party SDK internals.

None of this reaches Stripe unless STRIPE_SECRET_KEY is actually set —
see StripeNotConfiguredError, raised by every method here when it isn't.
"""

from __future__ import annotations

import logging
from typing import Optional

import stripe

from app.config import settings
from app.subscriptions.exceptions import StripeNotConfiguredError

logger = logging.getLogger(__name__)


class StripeClient:
    def __init__(self) -> None:
        if not settings.STRIPE_SECRET_KEY:
            raise StripeNotConfiguredError()
        # stripe-python's api_key is process-global; setting it per call
        # keeps this correct even if settings are overridden in tests.
        stripe.api_key = settings.STRIPE_SECRET_KEY

    def create_checkout_session(
        self,
        *,
        price_id: str,
        customer_id: Optional[str],
        customer_email: Optional[str],
        organization_id: str,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> "stripe.checkout.Session":
        """Create a Stripe Checkout Session for a subscription purchase."""
        kwargs = dict(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url or settings.STRIPE_SUCCESS_URL,
            cancel_url=cancel_url or settings.STRIPE_CANCEL_URL,
            client_reference_id=organization_id,
            metadata={"organization_id": organization_id},
        )
        if customer_id:
            kwargs["customer"] = customer_id
        elif customer_email:
            kwargs["customer_email"] = customer_email

        return stripe.checkout.Session.create(**kwargs)

    def create_billing_portal_session(
        self, *, customer_id: str, return_url: Optional[str] = None,
    ) -> "stripe.billing_portal.Session":
        """Create a Stripe Billing Portal session so a customer can self-manage billing."""
        return stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url or settings.STRIPE_SUCCESS_URL,
        )

    def cancel_subscription(self, *, stripe_subscription_id: str, at_period_end: bool = True):
        """Cancel a subscription — at the end of the current billing period by default."""
        if at_period_end:
            return stripe.Subscription.modify(
                stripe_subscription_id, cancel_at_period_end=True,
            )
        return stripe.Subscription.cancel(stripe_subscription_id)

    def retrieve_subscription(self, stripe_subscription_id: str):
        return stripe.Subscription.retrieve(stripe_subscription_id)

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> "stripe.Event":
        """
        Verify and parse a Stripe webhook payload.

        Raises stripe.error.SignatureVerificationError (propagated as-is)
        if the signature doesn't match — the caller is responsible for
        turning that into an HTTP 400.
        """
        return stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET,
        )
