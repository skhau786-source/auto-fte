"""
Pydantic schemas for the Warehouse Management module.

Defines request/response models for all warehouse API endpoints.
Uses Pydantic v2 features (Field, model_validator, field_validator).
"""

import uuid
from decimal import Decimal
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.inventory.constants import WarehouseStatus, TransferStatus


# ═══════════════════════════════════════════════════════════════════
# WAREHOUSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class WarehouseCreateRequest(BaseModel):
    """Request to create a new warehouse."""
    code: str = Field(..., min_length=1, max_length=50, description="Unique warehouse code")
    name: str = Field(..., min_length=1, max_length=255, description="Warehouse name")
    description: str | None = Field(None, max_length=5000, description="Warehouse description")

    # Address
    address: str | None = Field(None, max_length=500)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, max_length=20)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)

    # Contact
    phone: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)
    manager_id: uuid.UUID | None = None

    # Capacity
    capacity: int | None = Field(None, ge=0, description="Maximum storage capacity")
    capacity_unit: str = Field(default="units", max_length=20)

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        return v.upper().strip().replace(" ", "_")


class WarehouseUpdateRequest(BaseModel):
    """Request to update a warehouse (all fields optional — PATCH semantics)."""
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    phone: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)
    manager_id: uuid.UUID | None = None
    capacity: int | None = Field(None, ge=0)
    capacity_unit: str | None = Field(None, max_length=20)
    status: WarehouseStatus | None = None


class WarehouseOut(BaseModel):
    """Warehouse output model."""
    id: uuid.UUID
    store_id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    email: str | None = None
    manager_id: uuid.UUID | None = None
    capacity: int | None = None
    capacity_unit: str = "units"
    is_default: bool = False
    status: WarehouseStatus
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WarehouseListOut(BaseModel):
    """Paginated warehouse list."""
    items: list[WarehouseOut]
    total: int


class WarehouseActivateRequest(BaseModel):
    """Request to activate/deactivate a warehouse."""
    is_active: bool = True


# ═══════════════════════════════════════════════════════════════════
# DEFAULT WAREHOUSE & SETTINGS SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class DefaultWarehouseResponse(BaseModel):
    """Response when getting the default warehouse."""
    default_warehouse_id: str | None = None
    default_warehouse_name: str | None = None
    total_warehouses: int = 0
    active_warehouses: int = 0
    has_default: bool = False


class DefaultWarehouseSetResponse(BaseModel):
    """Response after setting the default warehouse."""
    warehouse_id: str
    warehouse_name: str
    message: str


class WarehouseSettingsOut(BaseModel):
    """Warehouse configuration settings output — all B.1 fields."""
    id: uuid.UUID | None = None
    store_id: uuid.UUID | None = None
    default_warehouse_id: str | None = None
    default_warehouse_name: str | None = None
    auto_allocate_inventory: bool = True
    multi_warehouse_enabled: bool = False
    allocation_strategy: str = "default_warehouse"
    allow_negative_stock: bool = False
    reserve_stock_on_order: bool = True
    auto_release_cancelled_orders: bool = True
    total_warehouses: int = 0
    active_warehouses: int = 0
    has_default: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class WarehouseSettingsUpdateRequest(BaseModel):
    """Request to update warehouse configuration settings (PATCH semantics)."""
    default_warehouse_id: uuid.UUID | None = Field(
        None, description="Set as default warehouse (None to clear)"
    )
    auto_allocate_inventory: bool | None = Field(
        None, description="Automatically allocate incoming stock to warehouses"
    )
    multi_warehouse_enabled: bool | None = Field(
        None, description="Allow inventory to be spread across multiple warehouses"
    )
    allocation_strategy: str | None = Field(
        None, description="Strategy for warehouse allocation: default_warehouse, highest_stock, nearest_warehouse, manual"
    )
    allow_negative_stock: bool | None = Field(
        None, description="Allow stock quantities to go below zero"
    )
    reserve_stock_on_order: bool | None = Field(
        None, description="Automatically reserve stock when order is placed"
    )
    auto_release_cancelled_orders: bool | None = Field(
        None, description="Automatically release reserved stock when order is cancelled"
    )


# ═══════════════════════════════════════════════════════════════════
# WAREHOUSE INVENTORY SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class WarehouseInventoryOut(BaseModel):
    """Per-warehouse inventory output model."""
    id: uuid.UUID
    warehouse_id: uuid.UUID
    product_id: uuid.UUID | None = None
    variant_id: uuid.UUID | None = None
    available_stock: int = 0
    reserved_stock: int = 0
    incoming_stock: int = 0
    damaged_stock: int = 0
    minimum_stock: int = 0
    maximum_stock: int | None = None
    reorder_point: int = 0
    bin_location: str | None = None
    shelf: str | None = None
    updated_at: datetime

    # Enriched fields (from aggregation)
    product_title: str | None = None
    variant_title: str | None = None
    sku: str | None = None
    total_stock: int = 0

    class Config:
        from_attributes = True


class WarehouseInventoryListOut(BaseModel):
    """Paginated warehouse inventory list."""
    items: list[WarehouseInventoryOut]
    total: int
    warehouse_id: uuid.UUID
    warehouse_name: str


class WarehouseInventoryUpdateRequest(BaseModel):
    """Request to update warehouse inventory levels."""
    available_stock: int | None = None
    reserved_stock: int | None = None
    incoming_stock: int | None = None
    damaged_stock: int | None = None
    minimum_stock: int | None = None
    maximum_stock: int | None = None
    reorder_point: int | None = None
    bin_location: str | None = None
    shelf: str | None = None


class WarehouseStockAdjustRequest(BaseModel):
    """Request to adjust stock at a warehouse."""
    variant_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity_change: int = Field(..., description="Positive to add, negative to remove")
    reason: str | None = Field(None, max_length=500)

    @field_validator("quantity_change")
    @classmethod
    def must_be_nonzero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("quantity_change must be non-zero")
        return v


class WarehouseStockAdjustResponse(BaseModel):
    """Response after warehouse stock adjustment."""
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    available_before: int
    available_after: int
    quantity_change: int
    transaction_id: uuid.UUID
    message: str


# ═══════════════════════════════════════════════════════════════════
# WAREHOUSE TRANSFER SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class TransferItemCreate(BaseModel):
    """A single item in a transfer request."""
    variant_id: uuid.UUID
    quantity: int = Field(..., ge=1, description="Quantity to transfer")
    reason: str | None = Field(None, max_length=500)


class TransferCreateRequest(BaseModel):
    """Request to create a warehouse transfer."""
    source_warehouse_id: uuid.UUID
    destination_warehouse_id: uuid.UUID
    items: list[TransferItemCreate] = Field(..., min_length=1, max_length=100)
    notes: str | None = Field(None, max_length=2000)
    transfer_date: datetime | None = None

    @model_validator(mode="after")
    def validate_different_warehouses(self):
        if self.source_warehouse_id == self.destination_warehouse_id:
            raise ValueError("Source and destination warehouses must be different")
        return self


class TransferItemOut(BaseModel):
    """Transfer item output."""
    id: uuid.UUID
    transfer_id: uuid.UUID
    product_id: uuid.UUID | None = None
    variant_id: uuid.UUID | None = None
    quantity: int
    received_quantity: int | None = None
    reason: str | None = None

    # Enriched
    product_title: str | None = None
    variant_title: str | None = None
    sku: str | None = None

    class Config:
        from_attributes = True


class TransferOut(BaseModel):
    """Transfer output model."""
    id: uuid.UUID
    store_id: uuid.UUID
    transfer_number: str
    source_warehouse_id: uuid.UUID
    destination_warehouse_id: uuid.UUID
    status: TransferStatus
    requested_by_id: uuid.UUID | None = None
    approved_by_id: uuid.UUID | None = None
    transfer_date: datetime | None = None
    completed_date: datetime | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[TransferItemOut] = []

    # Enriched
    source_warehouse_name: str | None = None
    destination_warehouse_name: str | None = None
    requested_by_name: str | None = None
    approved_by_name: str | None = None
    total_items: int = 0
    total_quantity: int = 0

    class Config:
        from_attributes = True


class TransferListOut(BaseModel):
    """Paginated transfer list."""
    items: list[TransferOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class TransferActionResponse(BaseModel):
    """Response after approving/completing a transfer."""
    transfer_id: uuid.UUID
    transfer_number: str
    status: TransferStatus
    message: str


# ═══════════════════════════════════════════════════════════════════
# CAPACITY SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class WarehouseCapacityOut(BaseModel):
    """Warehouse capacity information."""
    warehouse_id: uuid.UUID
    warehouse_name: str
    warehouse_code: str
    capacity: int | None = None
    capacity_unit: str = "units"
    current_usage: int = 0
    available_capacity: int | None = None
    usage_percentage: float | None = None
    status: str  # normal, warning, critical, exceeded

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════════
# ANALYTICS / DASHBOARD SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class WarehouseAnalyticsOut(BaseModel):
    """Warehouse analytics output."""
    warehouse_id: uuid.UUID
    warehouse_name: str
    total_products: int
    total_variants: int
    total_available_stock: int
    total_reserved_stock: int
    total_incoming_stock: int
    total_damaged_stock: int
    capacity_usage: WarehouseCapacityOut | None = None
    low_stock_count: int
    out_of_stock_count: int
    pending_transfers_in: int
    pending_transfers_out: int


class WarehouseSummaryOut(BaseModel):
    """High-level warehouse summary for dashboards."""
    total_warehouses: int
    active_warehouses: int
    total_capacity: int
    total_used_capacity: int
    total_products_in_warehouses: int
    total_transfers_pending: int
    total_transfers_in_transit: int
    warehouses: list[WarehouseCapacityOut] = []


# ═══════════════════════════════════════════════════════════════════
# RESERVATION SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class ReservationCreateRequest(BaseModel):
    """Request to reserve stock at a warehouse."""
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity: int = Field(..., ge=1)
    order_id: str | None = Field(None, max_length=255, description="Order ID from WooCommerce/Shopify")
    order_source: str | None = Field(None, description="Source: woocommerce, shopify, manual, api, ai_agent, transfer")
    expires_in_minutes: int | None = Field(None, ge=1, le=10080, description="Expiration in minutes (default 60, max 7 days)")
    reason: str | None = Field(None, max_length=500)


class ReservationReleaseRequest(BaseModel):
    """Request to release a stock reservation."""
    quantity: int | None = Field(None, ge=1, description="Quantity to release (None = release all)")
    reason: str | None = Field(None, max_length=500)


class ReservationOut(BaseModel):
    """Reservation output model — full lifecycle state."""
    id: uuid.UUID
    store_id: uuid.UUID
    warehouse_id: uuid.UUID
    inventory_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    variant_id: uuid.UUID | None = None
    order_id: str | None = None
    order_source: str = "manual"
    quantity: int
    status: str
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    released_at: datetime | None = None
    committed_at: datetime | None = None
    metadata: dict | None = None

    class Config:
        from_attributes = True


class ReservationListOut(BaseModel):
    """Paginated reservation list."""
    items: list[ReservationOut]
    total: int
    page: int = 1
    page_size: int = 20
    active_count: int = 0


class ReservationActionResponse(BaseModel):
    """Response after reservation commit/release/expire action."""
    reservation_id: uuid.UUID
    status: str
    message: str
    quantity: int


class ReservationDashboardOut(BaseModel):
    """Reservation dashboard widget data."""
    active_reservations: int
    reserved_stock_units: int
    expired_today: int
    reservation_success_rate: float
    reservations_by_source: dict[str, int] = {}


# ═══════════════════════════════════════════════════════════════════
# ALLOCATION SCHEMAS (Phase 4)
# ═══════════════════════════════════════════════════════════════════

class AllocationItemRequest(BaseModel):
    """A single item in an allocation request."""
    variant_id: uuid.UUID
    quantity: int = Field(..., ge=1)


class AllocationSettingsOut(BaseModel):
    """Allocation configuration output."""
    id: uuid.UUID | None = None
    store_id: uuid.UUID | None = None
    default_warehouse_id: str | None = None
    default_warehouse_name: str | None = None
    auto_allocate_inventory: bool = True
    multi_warehouse_enabled: bool = False
    allocation_strategy: str = "default_warehouse"
    allow_negative_stock: bool = False
    reserve_stock_on_order: bool = True
    auto_release_cancelled_orders: bool = True
    total_warehouses: int = 0
    active_warehouses: int = 0
    has_default: bool = False
    active_strategy: str = "default_warehouse"
    available_strategies: list[dict] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AllocationOrderRequest(BaseModel):
    """Request to allocate inventory for an order."""
    items: list[AllocationItemRequest] = Field(..., min_length=1, max_length=100)
    order_id: str | None = Field(None, max_length=255)
    strategy_name: str | None = None
    auto_reserve: bool = True


class AllocationOrderItem(BaseModel):
    """Per-item result in an order allocation."""
    variant_id: str
    requested: int
    fulfilled: int
    partial: bool = False
    fully_fulfilled: bool = False
    strategy: str = ""
    allocations: list[dict] = []


class AllocationOrderResponse(BaseModel):
    """Response after allocating inventory for an order."""
    order_id: str | None = None
    total_items: int = 0
    total_requested: int = 0
    total_fulfilled: int = 0
    fully_fulfilled: bool = False
    strategy_used: str = ""
    items: list[AllocationOrderItem] = []


class AllocationVariantRequest(BaseModel):
    """Request to allocate a single variant."""
    variant_id: uuid.UUID
    quantity: int = Field(..., ge=1)
    strategy_name: str | None = None
    warehouse_ids: list[uuid.UUID] | None = None
    auto_reserve: bool = False


class AllocatedWarehouseOut(BaseModel):
    """A single warehouse allocation in a response."""
    warehouse_id: str
    warehouse_name: str
    warehouse_code: str | None = None
    quantity: int
    available_before: int | None = None
    available_after: int | None = None


class AllocationVariantResponse(BaseModel):
    """Response after allocating a single variant."""
    variant_id: str
    requested_quantity: int
    fulfilled_quantity: int
    partial: bool = False
    fully_fulfilled: bool = False
    strategy: str = ""
    allocations: list[AllocatedWarehouseOut] = []


class AllocationPreviewResponse(BaseModel):
    """Response for preview allocation (no side effects)."""
    variant_id: str
    requested: int
    fulfilled: int
    partial: bool = False
    fully_fulfilled: bool = False
    strategy: str = ""
    allocations: list[AllocatedWarehouseOut] = []
    no_side_effects: bool = True


class AllocationReallocateRequest(BaseModel):
    """Request to reallocate stock between warehouses."""
    variant_id: uuid.UUID
    quantity: int = Field(..., ge=1)
    from_warehouse_id: uuid.UUID
    to_warehouse_id: uuid.UUID
    reason: str | None = Field(None, max_length=500)


class AllocationReallocateResponse(BaseModel):
    """Response after reallocating stock."""
    variant_id: str
    quantity: int
    from_warehouse_id: str
    from_warehouse_name: str
    to_warehouse_id: str
    to_warehouse_name: str
    reason: str | None = None


class AllocationStrategyOut(BaseModel):
    """Allocation strategy descriptor."""
    name: str
    class_name: str


class AllocationDashboardOut(BaseModel):
    """Allocation dashboard widget data."""
    allocation_strategy: str = "default_warehouse"
    multi_warehouse_enabled: bool = False
    total_warehouses: int = 0
    active_warehouses: int = 0
    total_capacity: int = 0
    total_usage: int = 0
    utilization_percentage: float = 0
    high_utilization_warehouses: int = 0
    top_fulfillment_warehouse_id: str | None = None
    top_fulfillment_warehouse_name: str | None = None


class AllocationValidateResponse(BaseModel):
    """Allocation validation result."""
    valid: bool
    warehouse_id: str | None = None
    warehouse_name: str | None = None
    warehouse_code: str | None = None
    variant_id: str | None = None
    available_stock: int = 0
    requested: int = 0
    reason: str | None = None
