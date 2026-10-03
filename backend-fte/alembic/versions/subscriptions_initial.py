"""subscriptions_initial — Create subscriptions/usage_records/stripe_webhook_events tables.

`app/subscriptions/models.py` (Subscription, UsageRecord) has existed
since early in this project — Organization.subscription_plan and
.stripe_customer_id already reference the concept — but, like
`organizations` (see organizations_teams_initial.py), no migration ever
actually created these tables. This migration creates exactly what the
models declare, plus a new `stripe_webhook_events` table (see
StripeWebhookEvent in models.py) needed for idempotent Stripe webhook
processing — Stripe does not guarantee at-most-once delivery, so the
Phase 3 payment integration records each processed event id before
acting on it.

Revision ID: subscriptions_initial
Revises: organizations_teams_initial
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = "subscriptions_initial"
down_revision = "organizations_teams_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id", UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column(
            "plan",
            sa.Enum("free", "starter", "professional", "enterprise",
                     name="plan_tier_enum"),
            nullable=False, server_default="free",
        ),
        sa.Column(
            "status",
            sa.Enum("active", "incomplete", "incomplete_expired", "past_due",
                     "canceled", "unpaid", "trialing", "paused",
                     name="subscription_status_enum"),
            nullable=False, server_default="active",
        ),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True, index=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True, index=True),
        sa.Column("stripe_price_id", sa.String(255), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_api_requests", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_storage_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "usage_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id", UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True),
            server_default=sa.func.now(), index=True,
        ),
        sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "stripe_webhook_events",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("event_type", sa.String(255), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("stripe_webhook_events")
    op.drop_table("usage_records")
    op.drop_table("subscriptions")
    sa.Enum(name="subscription_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="plan_tier_enum").drop(op.get_bind(), checkfirst=True)
