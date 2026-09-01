"""
Pydantic schemas for the WooCommerce Integration Module.

Defines request/response models for all API endpoints.
Uses Pydantic v2 features (Field, model_validator, field_validator).
"""

import uuid
from decimal import Decimal
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.woocommerce.constants import (
    OrderStatus,
    StockStatus,
    AlertType,
    AlertSeverity,
    SyncStatus,
    SyncType,
    StoreStatus,
)


# ═══════════════════════════════════════════════════════════════════
# STORE SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class StoreConnectRequest(BaseModel):
    """Request to connect a WooCommerce store."""
    store_name: str = Field(..., min_length=1, max_length=255, description="Friendly store name")
    store_url: str = Field(..., min_length=1, max_length=512, description="WooCommerce store URL (e.g., https://example.com)")
    consumer_key: str = Field(..., min_length=1, max_length=512, description="WooCommerce Consumer Key")
    consumer_secret: str = Field(..., min_length=1, max_length=512, description="WooCommerce Consumer Secret")

    @field_validator("store_url")
    @classmethod
    def validate_store_url(cls, v: str) -> str:
        v = v.rstrip("/")
        if not v.startswith(("http://", "https://")):
            raise ValueError("Store URL must start with http:// or https://")
        return v


class StoreVerifyResponse(BaseModel):
    """Response after verifying a WooCommerce store connection."""
    status: str
    store_url: str
    api_version: str
    woocommerce_version: str | None = None
    store_name: str | None = None


class StoreOut(BaseModel):
    """Store output model."""
    id: uuid.UUID
    store_name: str
    store_url: str
    status: StoreStatus
    is_active: bool
    wc_version: str | None = None
    last_sync_at: datetime | None = None
    webhooks_registered: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StoreListOut(BaseModel):
    """Paginated store list."""
    items: list[StoreOut]
    total: int


class StoreUpdateRequest(BaseModel):
    """Update store settings."""
    store_name: str | None = Field(None, min_length=1, max_length=255)
    consumer_key: str | None = Field(None, min_length=1, max_length=512)
    consumer_secret: str | None = Field(None, min_length=1, max_length=512)


# ═══════════════════════════════════════════════════════════════════
# PRODUCT SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class ProductOut(BaseModel):
    """Product output model."""
    id: uuid.UUID
    store_id: uuid.UUID
    wc_product_id: int
    type: str
    name: str
    slug: str | None = None
    sku: str | None = None
    barcode: str | None = None
    price: Decimal
    regular_price: Decimal
    sale_price: Decimal | None = None
    on_sale: bool = False
    featured_image_url: str | None = None
    manage_stock: bool = False
    stock_quantity: int | None = None
    stock_status: StockStatus
    total_sales: int = 0
    weight: str | None = None
    dimensions: dict | None = None
    shipping_class: str | None = None
    tax_status: str = "taxable"
    average_rating: str = "0"
    rating_count: int = 0
    featured: bool = False
    status: str = "publish"
    category_ids: list | None = None
    tag_ids: list | None = None
    attributes: list | None = None
    description: str | None = None
    short_description: str | None = None
    permalink: str | None = None
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductListOut(BaseModel):
    """Paginated product list."""
    items: list[ProductOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProductSearchFilters(BaseModel):
    """Product search and filter parameters."""
    search: str | None = Field(None, max_length=200)
    status: str | None = None
    stock_status: StockStatus | None = None
    category_id: int | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    on_sale: bool | None = None
    featured: bool | None = None
    type: str | None = None
    sku: str | None = Field(None, max_length=100)
    low_stock_only: bool = False


class ProductSyncRequest(BaseModel):
    """Request to manually trigger product sync."""
    force_full: bool = Field(False, description="If True, re-fetch ALL products from WooCommerce")


# ═══════════════════════════════════════════════════════════════════
# INVENTORY SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class InventoryAdjustRequest(BaseModel):
    """Request to adjust inventory stock."""
    wc_product_id: int = Field(..., description="WooCommerce product ID")
    quantity_change: int = Field(..., description="Positive to add stock, negative to remove")
    reason: str | None = Field(None, max_length=500)

    @field_validator("quantity_change")
    @classmethod
    def must_be_nonzero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("quantity_change must be non-zero")
        return v


class InventoryAdjustResponse(BaseModel):
    """Response after inventory adjustment."""
    product_id: uuid.UUID
    wc_product_id: int
    sku: str | None = None
    quantity_before: int
    quantity_after: int
    quantity_change: int
    message: str


class InventoryBulkAdjustRequest(BaseModel):
    """Bulk inventory adjustment request."""
    adjustments: list[InventoryAdjustRequest] = Field(..., min_length=1, max_length=100)


class LowStockItemOut(BaseModel):
    """Low stock alert item."""
    product_id: uuid.UUID
    wc_product_id: int
    product_name: str
    sku: str | None = None
    stock_quantity: int
    low_stock_threshold: int = 10
    featured_image_url: str | None = None


class LowStockListOut(BaseModel):
    """Paginated low stock list."""
    items: list[LowStockItemOut]
    total: int


class InventoryHistoryOut(BaseModel):
    """Inventory audit log entry."""
    id: uuid.UUID
    product_id: uuid.UUID | None = None
    wc_product_id: int
    sku: str | None = None
    action: str
    quantity_before: int | None = None
    quantity_after: int | None = None
    quantity_change: int | None = None
    reason: str | None = None
    source: str
    performed_by: uuid.UUID | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════════
# ORDER SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class OrderItemOut(BaseModel):
    """Order line item output."""
    id: uuid.UUID
    wc_order_item_id: int
    wc_product_id: int
    name: str
    sku: str | None = None
    quantity: int
    price: Decimal
    total: Decimal
    total_tax: Decimal

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    """Order output model."""
    id: uuid.UUID
    store_id: uuid.UUID
    wc_order_id: int
    number: str
    status: OrderStatus
    currency: str
    customer_id: int
    billing: dict | None = None
    shipping: dict | None = None
    payment_method_title: str | None = None
    discount_total: Decimal
    shipping_total: Decimal
    total: Decimal
    total_tax: Decimal
    coupon_lines: list | None = None
    date_paid: str | None = None
    date_completed: str | None = None
    customer_note: str | None = None
    last_synced_at: datetime | None = None
    items: list[OrderItemOut] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrderListOut(BaseModel):
    """Paginated order list."""
    items: list[OrderOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class OrderSyncRequest(BaseModel):
    """Request to sync orders."""
    date_after: str | None = Field(None, description="ISO 8601 date to sync orders after")
    status: str | None = None


# ═══════════════════════════════════════════════════════════════════
# CUSTOMER SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class CustomerOut(BaseModel):
    """Customer output model."""
    id: uuid.UUID
    store_id: uuid.UUID
    wc_customer_id: int
    email: str
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    role: str = "customer"
    avatar_url: str | None = None
    billing: dict | None = None
    shipping: dict | None = None
    orders_count: int = 0
    total_spent: Decimal
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CustomerListOut(BaseModel):
    """Paginated customer list."""
    items: list[CustomerOut]
    total: int
    page: int
    page_size: int
    total_pages: int


# ═══════════════════════════════════════════════════════════════════
# CATEGORY SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class CategoryOut(BaseModel):
    """Category output model."""
    id: uuid.UUID
    store_id: uuid.UUID
    wc_category_id: int
    name: str
    slug: str
    description: str | None = None
    parent_id: uuid.UUID | None = None
    wc_parent_id: int = 0
    image_url: str | None = None
    display: str = "default"
    menu_order: int = 0
    product_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class CategoryListOut(BaseModel):
    """Paginated category list."""
    items: list[CategoryOut]
    total: int


class CategoryTreeOut(BaseModel):
    """Category tree node with children."""
    id: uuid.UUID
    wc_category_id: int
    name: str
    slug: str
    description: str | None = None
    parent_id: uuid.UUID | None = None
    product_count: int = 0
    children: list["CategoryTreeOut"] = []


# ═══════════════════════════════════════════════════════════════════
# COUPON SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class CouponOut(BaseModel):
    """Coupon output model."""
    id: uuid.UUID
    store_id: uuid.UUID
    wc_coupon_id: int
    code: str
    amount: Decimal
    discount_type: str
    description: str | None = None
    date_expires: str | None = None
    usage_count: int = 0
    individual_use: bool = False
    usage_limit: int | None = None
    usage_limit_per_user: int | None = None
    free_shipping: bool = False
    exclude_sale_items: bool = False
    minimum_amount: str | None = None
    maximum_amount: str | None = None
    email_restrictions: list | None = None
    product_ids: list | None = None
    product_categories: list | None = None
    last_synced_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class CouponListOut(BaseModel):
    """Paginated coupon list."""
    items: list[CouponOut]
    total: int


# ═══════════════════════════════════════════════════════════════════
# ALERT SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class AlertOut(BaseModel):
    """Alert output model."""
    id: uuid.UUID
    store_id: uuid.UUID
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    resource_type: str | None = None
    resource_id: str | None = None
    is_read: bool = False
    is_resolved: bool = False
    meta_data: dict | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class AlertListOut(BaseModel):
    """Paginated alert list."""
    items: list[AlertOut]
    total: int
    unread_count: int = 0


class AlertMarkRequest(BaseModel):
    """Mark alerts as read/resolved."""
    alert_ids: list[uuid.UUID] = Field(..., min_length=1)
    mark_as_read: bool = True
    mark_as_resolved: bool = False


# ═══════════════════════════════════════════════════════════════════
# SYNC SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class SyncRequest(BaseModel):
    """Request to trigger a sync."""
    resources: list[str] = Field(default=["products", "orders", "customers", "categories", "coupons"])
    force_full: bool = False


class SyncResponse(BaseModel):
    """Sync operation response."""
    sync_id: uuid.UUID
    store_id: uuid.UUID
    sync_type: SyncType
    resources: list[str]
    status: SyncStatus
    message: str


class SyncLogOut(BaseModel):
    """Sync log output model."""
    id: uuid.UUID
    store_id: uuid.UUID
    sync_type: SyncType
    resource: str
    status: SyncStatus
    total_items: int = 0
    created_items: int = 0
    updated_items: int = 0
    failed_items: int = 0
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class SyncLogListOut(BaseModel):
    """Paginated sync log list."""
    items: list[SyncLogOut]
    total: int


# ═══════════════════════════════════════════════════════════════════
# DASHBOARD SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class DashboardStats(BaseModel):
    """Dashboard statistics."""
    total_products: int
    total_orders: int
    total_customers: int
    total_categories: int
    total_coupons: int
    total_revenue: Decimal = Decimal("0.00")
    low_stock_count: int
    out_of_stock_count: int
    active_alerts: int
    last_sync_at: datetime | None = None
    sync_status: str = "unknown"
    orders_today: int = 0
    revenue_today: Decimal = Decimal("0.00")


class DashboardOut(BaseModel):
    """Full dashboard output."""
    stats: DashboardStats
    recent_orders: list[OrderOut] = []
    low_stock_items: list[LowStockItemOut] = []
    recent_alerts: list[AlertOut] = []
    recent_syncs: list[SyncLogOut] = []


# ═══════════════════════════════════════════════════════════════════
# SETTINGS SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class SettingsOut(BaseModel):
    """Store settings output."""
    id: uuid.UUID
    store_id: uuid.UUID
    auto_sync_enabled: bool = True
    sync_interval_hours: int = 6
    sync_products: bool = True
    sync_orders: bool = True
    sync_customers: bool = True
    sync_categories: bool = True
    sync_coupons: bool = True
    low_stock_threshold: int = 10
    low_stock_alerts: bool = True
    sync_failure_alerts: bool = True
    email_alerts: bool = False
    alert_email: str | None = None
    retention_days: int = 90

    class Config:
        from_attributes = True


class SettingsUpdateRequest(BaseModel):
    """Update store settings."""
    auto_sync_enabled: bool | None = None
    sync_interval_hours: int | None = Field(None, ge=1, le=168)
    sync_products: bool | None = None
    sync_orders: bool | None = None
    sync_customers: bool | None = None
    sync_categories: bool | None = None
    sync_coupons: bool | None = None
    low_stock_threshold: int | None = Field(None, ge=0)
    low_stock_alerts: bool | None = None
    sync_failure_alerts: bool | None = None
    email_alerts: bool | None = None
    alert_email: str | None = None
    retention_days: int | None = Field(None, ge=1, le=365)


# ═══════════════════════════════════════════════════════════════════
# WEBHOOK SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class WebhookPayload(BaseModel):
    """Generic WooCommerce webhook payload wrapper."""
    topic: str
    resource_id: int
    store_url: str
    signature: str | None = None
    body: dict = {}


class WebhookRegistrationResponse(BaseModel):
    """Webhook registration result."""
    topic: str
    id: int | None = None
    status: str
    error: str | None = None


# ═══════════════════════════════════════════════════════════════════
# GENERIC RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
# BULK IMPORT / EXPORT SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class BulkImportItem(BaseModel):
    """Single product for bulk import."""
    sku: str | None = Field(None, description="Product SKU (used for matching)")
    wc_product_id: int | None = Field(None, description="WooCommerce product ID")
    name: str = Field(..., min_length=1, max_length=512, description="Product name")
    price: Decimal | None = Field(None, ge=0)
    regular_price: Decimal | None = Field(None, ge=0)
    sale_price: Decimal | None = Field(None, ge=0)
    stock_quantity: int | None = Field(None, ge=0)
    stock_status: str | None = None
    manage_stock: bool | None = None
    description: str | None = None
    short_description: str | None = None
    weight: str | None = None
    barcode: str | None = None
    status: str | None = None
    type: str | None = None
    featured_image_url: str | None = None
    tax_status: str | None = None
    tax_class: str | None = None
    backorders: str | None = None
    featured: bool | None = None


class BulkImportRequest(BaseModel):
    """Bulk import request."""
    items: list[BulkImportItem] = Field(..., min_length=1, max_length=5000, description="Products to import (max 5000)")
    format: str = Field(default="json", pattern=r"^(json|csv)$")
    raw_data: str | None = Field(None, description="Raw CSV or JSON string (alternative to items)")


class BulkImportResponse(BaseModel):
    """Bulk import response."""
    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[dict] = []


class BulkUpdateItem(BaseModel):
    """Single product for bulk update."""
    sku: str | None = Field(None, description="Product SKU (used for matching)")
    wc_product_id: int | None = Field(None, description="WooCommerce product ID")
    name: str | None = None
    price: Decimal | None = Field(None, ge=0)
    regular_price: Decimal | None = Field(None, ge=0)
    sale_price: Decimal | None = Field(None, ge=0)
    stock_quantity: int | None = Field(None, ge=0)
    stock_status: str | None = None
    manage_stock: bool | None = None
    description: str | None = None
    short_description: str | None = None
    weight: str | None = None
    barcode: str | None = None
    status: str | None = None
    featured_image_url: str | None = None


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    detail: dict | None = None


class ErrorResponse(BaseModel):
    """Error response."""
    detail: str
    error_code: str | None = None
    errors: list[dict] | None = None


class PaginationParams(BaseModel):
    """Common pagination parameters."""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ═══════════════════════════════════════════════════════════════════
# ANALYTICS SCHEMAS (Revenue Dashboard / Advanced Analytics)
# ═══════════════════════════════════════════════════════════════════

class RevenueTrendPointOut(BaseModel):
    """One day's revenue/order count within a revenue trend."""
    date: str
    revenue: float
    orders: int


class RevenueAnalyticsOut(BaseModel):
    """Revenue summary + daily trend for a period, compared to the prior period."""
    period_days: int
    period_start: datetime
    period_end: datetime
    revenue: float
    orders: int
    average_order_value: float
    previous_period_revenue: float
    previous_period_orders: int
    revenue_change_pct: Optional[float] = None
    order_change_pct: Optional[float] = None
    trend: list[RevenueTrendPointOut] = []


class TopProductOut(BaseModel):
    """A product's realized revenue/units sold within a period."""
    wc_product_id: int
    name: str
    sku: Optional[str] = None
    revenue: float
    units_sold: int


class TopProductsOut(BaseModel):
    products: list[TopProductOut] = []


class OrderStatusCountOut(BaseModel):
    status: str
    count: int


class OrderStatusBreakdownOut(BaseModel):
    period_days: int
    breakdown: list[OrderStatusCountOut] = []
