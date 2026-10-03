"""Domain exceptions for the subscriptions/billing module."""


class SubscriptionError(Exception):
    """Base class for all subscription/billing errors."""


class StripeNotConfiguredError(SubscriptionError):
    """Raised when a billing endpoint is invoked without STRIPE_SECRET_KEY set."""

    def __init__(self) -> None:
        super().__init__(
            "Stripe is not configured on this deployment "
            "(STRIPE_SECRET_KEY is empty) — billing endpoints are unavailable "
            "until it is set."
        )


class UnknownPlanError(SubscriptionError):
    """Raised when a requested plan/interval has no configured Stripe price id."""

    def __init__(self, plan: str, interval: str) -> None:
        self.plan = plan
        self.interval = interval
        super().__init__(
            f"No Stripe price configured for plan='{plan}' interval='{interval}' "
            f"(set STRIPE_PRICE_{plan.upper()}_{interval.upper()})"
        )


class SubscriptionNotFoundError(SubscriptionError):
    """Raised when an organization has no active subscription to act on."""

    def __init__(self, organization_id) -> None:
        self.organization_id = organization_id
        super().__init__(f"No active subscription for organization {organization_id}")


class InvalidWebhookSignatureError(SubscriptionError):
    """Raised when a Stripe webhook payload fails signature verification."""
