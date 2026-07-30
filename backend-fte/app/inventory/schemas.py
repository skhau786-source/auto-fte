import uuid
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.inventory.constants import TransactionType


# ─── Product CRUD Schemas ───

class VariantCreateRequest(BaseModel):
    """Used inside ProductCreateRequest for inline variant creation."""
    title: str = Field(..., min_length=1, max_length=255)
    sku: str | None = Field(None, max_length=100)
    barcode: str | None = Field(None, max_length=100)
    price: Decimal = Field(default=Decimal("0.00"), ge=0)
    compare_at_price: Decimal | None = None
    inventory_quantity: int = Field(default=0, ge=0)
    requires_shipping: bool = True
    low_stock_threshold: int | None = Field(default=10, ge=0)


class VariantUpdateRequest(BaseModel):
    """All fields optional — only send what changed."""
    title: str | None = Field(None, min_length=1, max_length=255)
    sku: str | None = Field(None, max_length=100)
    barcode: str | None = Field(None, max_length=100)
    price: Decimal | None = Field(None, ge=0)
    compare_at_price: Decimal | None = None  # Set to 0 or None to clear
    inventory_quantity: int | None = Field(None, ge=0)
    requires_shipping: bool | None = None
    low_stock_threshold: int | None = None


class ProductCreateRequest(BaseModel):
    """
    Create a product locally (PostgreSQL only).
    shopify_product_id is not required — it gets populated after Shopify sync.
    """
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    vendor: str | None = Field(None, max_length=255)
    product_type: str | None = Field(None, max_length=255)
    status: str = Field(default="active", pattern=r"^(active|archived|draft)$")
    category_id: uuid.UUID | None = None
    featured_image_url: str | None = Field(None, max_length=1024)
    variants: list[VariantCreateRequest] = Field(default_factory=list, max_length=20)


class ProductUpdateRequest(BaseModel):
    """All fields optional — partial update (PATCH semantics)."""
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    vendor: str | None = Field(None, max_length=255)
    product_type: str | None = Field(None, max_length=255)
    status: str | None = Field(None, pattern=r"^(active|archived|draft)$")
    category_id: uuid.UUID | None = None  # Set to None to clear category
    featured_image_url: str | None = None
    variants: list[VariantUpdateRequest] | None = None


class DeleteResponse(BaseModel):
    message: str
    deleted_product_id: uuid.UUID


# ─── Product Output Schemas ───

class ProductVariantOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    shopify_variant_id: int | None  # None for local-only variants
    shopify_inventory_item_id: int | None
    title: str
    sku: str | None
    barcode: str | None
    price: Decimal
    compare_at_price: Decimal | None
    inventory_quantity: int
    requires_shipping: bool
    low_stock_threshold: int | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductOut(BaseModel):
    id: uuid.UUID
    store_id: uuid.UUID
    category_id: uuid.UUID | None
    shopify_product_id: int | None  # None for local-only products
    title: str
    description: str | None
    vendor: str | None
    product_type: str | None
    status: str
    featured_image_url: str | None
    created_at: datetime
    updated_at: datetime
    last_synced_at: datetime | None
    variants: list[ProductVariantOut] = []

    class Config:
        from_attributes = True


class ProductListOut(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProductSearchFilters(BaseModel):
    search: str | None = Field(None, max_length=200)
    status: str | None = Field(None, pattern=r"^(active|archived|draft)$")
    category_id: uuid.UUID | None = None
    vendor: str | None = Field(None, max_length=255)
    product_type: str | None = Field(None, max_length=255)
    low_stock_only: bool = False
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


# ─── Category Schemas ───

class CategoryOut(BaseModel):
    id: uuid.UUID
    store_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    parent_id: uuid.UUID | None
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Inventory Adjustment Schemas ───

class InventoryAdjustRequest(BaseModel):
    variant_id: uuid.UUID
    quantity_change: int = Field(..., description="Positive to add stock, negative to remove")
    reason: str | None = Field(None, max_length=500)

    @field_validator("quantity_change")
    @classmethod
    def must_be_nonzero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("quantity_change must be non-zero (positive to add, negative to remove)")
        return v


class InventoryBulkAdjustRequest(BaseModel):
    adjustments: list[InventoryAdjustRequest] = Field(..., min_length=1, max_length=100)


class InventoryAdjustResponse(BaseModel):
    variant_id: uuid.UUID
    quantity_before: int
    quantity_after: int
    quantity_change: int
    transaction_id: uuid.UUID
    synced_to_shopify: bool
    message: str


class BulkAdjustItemResult(BaseModel):
    variant_id: uuid.UUID
    quantity_before: int | None = None
    quantity_after: int | None = None
    quantity_change: int | None = None
    transaction_id: uuid.UUID | None = None
    synced_to_shopify: bool | None = None
    error: str | None = None
    success: bool


# ─── Sync Schemas ───

class SyncRequest(BaseModel):
    force_full: bool = Field(False, description="If True, re-fetch ALL products from Shopify")


class SyncResponse(BaseModel):
    products_created: int
    products_updated: int
    variants_created: int
    variants_updated: int
    inventory_updated: int
    message: str


# ─── History / Transaction Schemas ───

class InventoryTransactionOut(BaseModel):
    id: uuid.UUID
    variant_id: uuid.UUID
    transaction_type: str
    quantity_change: int
    quantity_before: int
    quantity_after: int
    reason: str | None
    reference_id: str | None
    performed_by: uuid.UUID | None
    synced_to_shopify: bool
    created_at: datetime

    class Config:
        from_attributes = True


class InventoryHistoryOut(BaseModel):
    items: list[InventoryTransactionOut]
    total: int
    page: int
    page_size: int


class InventoryHistoryParams(BaseModel):
    variant_id: uuid.UUID | None = None
    transaction_type: TransactionType | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ─── Low Stock Schemas ───

class LowStockItemOut(BaseModel):
    variant_id: uuid.UUID
    variant_title: str
    sku: str | None
    product_title: str
    product_id: uuid.UUID
    inventory_quantity: int
    low_stock_threshold: int
    days_until_out: float | None = None

    class Config:
        from_attributes = True


class LowStockListOut(BaseModel):
    items: list[LowStockItemOut]
    total: int


class SetThresholdRequest(BaseModel):
    variant_id: uuid.UUID
    threshold: int = Field(..., ge=0, description="Low-stock threshold (0 to disable)")


# ─── Dashboard / Reports ───

class InventoryDashboardOut(BaseModel):
    total_products: int
    total_variants: int
    total_inventory_units: int
    total_value: Decimal
    low_stock_count: int
    out_of_stock_count: int
    recent_transactions: list[InventoryTransactionOut] = []
    top_low_stock: list[LowStockItemOut] = []


class InventoryReportOut(BaseModel):
    period_start: datetime
    period_end: datetime
    total_adjustments: int
    total_sales: int
    total_purchases: int
    total_returns: int
    net_change: int


# ─── Bulk Import / Export Schemas ───

class BulkImportRow(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    inventory_quantity: int = Field(..., ge=0)
    price: Decimal | None = None


class BulkImportRequest(BaseModel):
    items: list[BulkImportRow] = Field(..., min_length=1, max_length=1000)


class BulkImportResponse(BaseModel):
    total_processed: int
    succeeded: int
    failed: int
    errors: list[dict] = []


# ─── Store (for dependency injection, not a DB model schema) ───

class StoreOut(BaseModel):
    id: uuid.UUID
    shopify_domain: str
    shopify_store_id: int | None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
