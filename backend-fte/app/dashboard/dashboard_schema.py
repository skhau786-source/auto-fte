"""
Dashboard schemas for the Inventory Monitoring Dashboard.

Exposes aggregate inventory metrics and health information
for the authenticated store.
"""

import uuid
from decimal import Decimal
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field


class DashboardSummary(BaseModel):
    """Aggregated inventory summary for the store."""
    total_products: int = 0
    total_variants: int = 0
    total_inventory_units: int = 0
    total_inventory_value: Decimal = Decimal("0.00")
    low_stock_count: int = 0
    out_of_stock_count: int = 0
    category_count: int = 0


class TodayTransactionSummary(BaseModel):
    """Counts of today's transactions by type."""
    total: int = 0
    adjustments: int = 0
    shopify_syncs: int = 0
    low_stock_alerts: int = 0


class SyncHealthSummary(BaseModel):
    """Current sync health status."""
    pending_syncs: int = 0
    failed_syncs: int = 0
    dead_letter_count: int = 0
    average_sync_time_ms: Optional[float] = None
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None  # "success", "failed", "none"


class WebhookHealthSummary(BaseModel):
    """Webhook processing health."""
    total_received_24h: int = 0
    last_webhook_at: Optional[datetime] = None
    errors_24h: int = 0
    webhooks_registered: list[str] = []


class RecentErrorItem(BaseModel):
    """A single recent error entry."""
    id: uuid.UUID
    action: str
    details: dict[str, Any] = {}
    created_at: datetime
    variant_id: Optional[uuid.UUID] = None


class DashboardResponse(BaseModel):
    """Complete dashboard response."""
    inventory_summary: DashboardSummary
    today_transactions: TodayTransactionSummary
    sync_health: SyncHealthSummary
    webhook_health: WebhookHealthSummary
    recent_errors: list[RecentErrorItem] = []
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    store_id: uuid.UUID
    store_domain: str
