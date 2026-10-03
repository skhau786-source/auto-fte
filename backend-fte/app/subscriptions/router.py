"""
API Router for subscriptions / Stripe billing.

Thin router layer — all business logic lives in SubscriptionService.

Endpoints:
  GET  /subscriptions/me               — Current organization's subscription
  POST /subscriptions/checkout         — Create a Stripe Checkout session (upgrade)
  POST /subscriptions/portal           — Create a Stripe Billing Portal session
  POST /subscriptions/cancel           — Cancel at period end
  POST /subscriptions/webhooks/stripe  — Stripe webhook receiver (no user auth —
                                          authenticated by Stripe signature instead)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent
from app.organizations.dependencies import get_current_organization, require_permission
from app.organizations.models import Organization, Permission

from app.subscriptions.service import SubscriptionService
from app.subscriptions.schemas import (
    CheckoutSessionRequest, CheckoutSessionOut, BillingPortalOut,
    SubscriptionOut, CancelSubscriptionOut, WebhookResultOut,
)
from app.subscriptions.exceptions import (
    SubscriptionError,
    StripeNotConfiguredError,
    UnknownPlanError,
    SubscriptionNotFoundError,
    InvalidWebhookSignatureError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


def _handle_error(exc: SubscriptionError) -> None:
    if isinstance(exc, StripeNotConfiguredError):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    if isinstance(exc, UnknownPlanError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, SubscriptionNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/me", response_model=Optional[SubscriptionOut], summary="Get current subscription")
async def get_my_subscription(
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db=db)
    sub = await service.get_organization_subscription(org.id)
    if sub is None:
        return None
    return SubscriptionOut(
        id=str(sub.id),
        organization_id=str(sub.organization_id),
        plan=sub.plan.value,
        status=sub.status.value,
        stripe_customer_id=sub.stripe_customer_id,
        stripe_subscription_id=sub.stripe_subscription_id,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        canceled_at=sub.canceled_at,
        trial_end=sub.trial_end,
        is_active=sub.is_active,
    )


@router.post(
    "/checkout",
    response_model=CheckoutSessionOut,
    summary="Create a Stripe Checkout session to upgrade plan",
)
async def create_checkout_session(
    payload: CheckoutSessionRequest,
    org: Organization = Depends(get_current_organization),
    user: RegisteredStudent = Depends(get_current_user),
    _: bool = Depends(require_permission(Permission.SETTINGS_BILLING)),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db=db)
    try:
        checkout_url = await service.create_checkout_session(
            organization_id=org.id,
            plan=payload.plan,
            interval=payload.interval,
            customer_email=getattr(user, "email", None),
        )
    except SubscriptionError as exc:
        _handle_error(exc)
    return CheckoutSessionOut(checkout_url=checkout_url)


@router.post(
    "/portal",
    response_model=BillingPortalOut,
    summary="Create a Stripe Billing Portal session",
)
async def create_billing_portal_session(
    org: Organization = Depends(get_current_organization),
    _: bool = Depends(require_permission(Permission.SETTINGS_BILLING)),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db=db)
    try:
        portal_url = await service.create_billing_portal_session(org.id)
    except SubscriptionError as exc:
        _handle_error(exc)
    return BillingPortalOut(portal_url=portal_url)


@router.post(
    "/cancel",
    response_model=CancelSubscriptionOut,
    summary="Cancel subscription at period end",
)
async def cancel_subscription(
    org: Organization = Depends(get_current_organization),
    _: bool = Depends(require_permission(Permission.SETTINGS_BILLING)),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db=db)
    try:
        sub = await service.cancel_subscription(org.id)
    except SubscriptionError as exc:
        _handle_error(exc)
    return CancelSubscriptionOut(
        id=str(sub.id),
        status=sub.status.value,
        canceled_at=sub.canceled_at,
        message="Subscription will be canceled at the end of the current billing period.",
    )


@router.post(
    "/webhooks/stripe",
    response_model=WebhookResultOut,
    summary="Stripe webhook receiver",
)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    No user authentication — Stripe calls this endpoint directly.
    Authenticity is instead established by verifying the
    `Stripe-Signature` header against STRIPE_WEBHOOK_SECRET
    (SubscriptionService.handle_webhook_event -> StripeClient.construct_webhook_event).
    An invalid signature is rejected with 400 so Stripe's retry logic
    knows the delivery didn't succeed; everything else returns 200 so
    Stripe doesn't keep retrying events we've already recorded.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    service = SubscriptionService(db=db)
    try:
        result = await service.handle_webhook_event(payload, sig_header)
    except InvalidWebhookSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except StripeNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    return WebhookResultOut(**result)
