"""
Unified Dashboard Schema — Phase 7.

Combines metrics from all 6 completed phases into a single
comprehensive dashboard response for frontend widgets.

Sections:
- Phase 1: Inventory Summary (products, variants, low stock)
- Phase 2: Warehouse Summary (warehouses, capacity, transfers)
- Phase 3: Reservation Summary (active reservations, success rate)
- Phase 4: Allocation Summary (strategy, utilization)
- Phase 5: Order Integration Summary (allocated, committed, released)
- Phase 6: Aggregation Summary (total available/reserved/incoming/damaged, value)
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════
# Phase 1 — Inventory Summary
# ═══════════════════════════════════════════════════════════════════

class InventorySummaryWidget(BaseModel):
    """Phase 1: Core inventory metrics."""
    total_products: int = 0
    total_variants: int = 0
    total_inventory_units: int = 0
    total_inventory_value: Decimal = Decimal("0.00")
    low_stock_count: int = 0
    out_of_stock_count: int = 0
    category_count: int = 0


# ═══════════════════════════════════════════════════════════════════
# Phase 2 — Warehouse Summary
# ═══════════════════════════════════════════════════════════════════

class WarehouseSummaryWidget(BaseModel):
    """Phase 2: Warehouse management metrics."""
    total_warehouses: int = 0
    active_warehouses: int = 0
    total_capacity: int = 0
    total_used_capacity: int = 0
    capacity_usage_percentage: float = 0.0
    pending_transfers: int = 0
    in_transit_transfers: int = 0
    low_stock_warehouse_items: int = 0
    default_warehouse_name: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════
# Phase 3 — Reservation Summary
# ═══════════════════════════════════════════════════════════════════

class ReservationSummaryWidget(BaseModel):
    """Phase 3: Reservation engine metrics."""
    active_reservations: int = 0
    reserved_stock_units: int = 0
    expired_today: int = 0
    reservation_success_rate: float = 100.0
    reservations_by_source: dict[str, int] = {}


# ═══════════════════════════════════════════════════════════════════
# Phase 4 — Allocation Summary
# ═══════════════════════════════════════════════════════════════════

class WarehouseUtilizationItem(BaseModel):
    """Per-warehouse utilization for allocation dashboard."""
    warehouse_id: str
    warehouse_name: str
    capacity: Optional[int] = None
    current_usage: int = 0
    usage_percentage: Optional[float] = None
    status: str = "normal"


class AllocationSummaryWidget(BaseModel):
    """Phase 4: Allocation engine metrics."""
    allocation_strategy: str = "default_warehouse"
    multi_warehouse_enabled: bool = False
    total_warehouses: int = 0
    active_warehouses: int = 0
    total_capacity: int = 0
    total_usage: int = 0
    utilization_percentage: float = 0.0
    high_utilization_warehouses: int = 0
    top_fulfillment_warehouse_name: Optional[str] = None
    warehouse_utilization: list[WarehouseUtilizationItem] = []


# ═══════════════════════════════════════════════════════════════════
# Phase 5 — Order Integration Summary
# ═══════════════════════════════════════════════════════════════════

class OrderIntegrationSummaryWidget(BaseModel):
    """Phase 5: WooCommerce order integration metrics."""
    orders_waiting_allocation: int = 0
    reserved_orders: int = 0
    partially_fulfilled_orders: int = 0
    committed_orders: int = 0
    released_reservations: int = 0
    allocation_success_rate: float = 100.0
    reservation_success_rate: float = 100.0


# ═══════════════════════════════════════════════════════════════════
# Phase 6 — Aggregation Summary
# ═══════════════════════════════════════════════════════════════════

class AggregationSummaryWidget(BaseModel):
    """Phase 6: Inventory aggregation metrics."""
    total_available_inventory: int = 0
    total_reserved_inventory: int = 0
    total_incoming_inventory: int = 0
    total_damaged_inventory: int = 0
    inventory_value: float = 0.0
    warehouse_count: int = 0
    active_reservations_count: int = 0
    transfer_in_transit_count: int = 0


# ═══════════════════════════════════════════════════════════════════
# Unified Dashboard Response
# ═══════════════════════════════════════════════════════════════════

class UnifiedDashboardResponse(BaseModel):
    """Complete unified dashboard combining all 6 phases."""
    # Store context
    store_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # Phase 1
    inventory: InventorySummaryWidget = Field(default_factory=InventorySummaryWidget)

    # Phase 2
    warehouse: WarehouseSummaryWidget = Field(default_factory=WarehouseSummaryWidget)

    # Phase 3
    reservation: ReservationSummaryWidget = Field(default_factory=ReservationSummaryWidget)

    # Phase 4
    allocation: AllocationSummaryWidget = Field(default_factory=AllocationSummaryWidget)

    # Phase 5
    order_integration: OrderIntegrationSummaryWidget = Field(
        default_factory=OrderIntegrationSummaryWidget,
    )

    # Phase 6
    aggregation: AggregationSummaryWidget = Field(
        default_factory=AggregationSummaryWidget,
    )
