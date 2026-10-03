"""Request/response schemas for the subscriptions/billing API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CheckoutSessionRequest(BaseModel):
    plan: str = Field(..., description="Target plan tier: starter | professional | enterprise")
    interval: str = Field("monthly", description="monthly | yearly")


class CheckoutSessionOut(BaseModel):
    checkout_url: str


class BillingPortalOut(BaseModel):
    portal_url: str


class SubscriptionOut(BaseModel):
    id: str
    organization_id: str
    plan: str
    status: str
    stripe_customer_id: Optional[str]
    stripe_subscription_id: Optional[str]
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    canceled_at: Optional[datetime]
    trial_end: Optional[datetime]
    is_active: bool

    model_config = {"from_attributes": True}


class CancelSubscriptionOut(BaseModel):
    id: str
    status: str
    canceled_at: Optional[datetime]
    message: str


class WebhookResultOut(BaseModel):
    received: bool
    event_type: Optional[str] = None
    duplicate: bool = False
