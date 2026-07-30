"""
SQLAlchemy ORM models for the WooCommerce Integration Module.

Adds WooCommerce-specific entities to the existing Digital FTE database schema.
All models use UUID primary keys and include created_at/updated_at timestamps.

Tables:
- wc_stores: WooCommerce store connections
- wc_products: Products synced from WooCommerce
- wc_product_variants: Product variations (variable products)
- wc_categories: Product categories
- wc_tags: Product tags
- wc_customers: Customers synced from WooCommerce
- wc_orders: Orders synced from WooCommerce
- wc_order_items: Individual line items within orders
- wc_coupons: Coupons synced from WooCommerce
- wc_inventory_logs: Inventory change audit trail
- wc_alerts: System alerts (low stock, sync failures, etc.)
- wc_sync_logs: Sync operation history
- wc_settings: Store-specific settings
"""

import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy import (
    String, Boolean, DateTime, ForeignKey, Enum, func, Text,
    Integer, BigInteger, Numeric, Float, JSON, text as sa_text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.woocommerce.constants import (
    SyncStatus,
    SyncType,
    OrderStatus,
    StockStatus,
    AlertType,
    AlertSeverity,
    StoreStatus,
)


class WooCommerceStore(Base):
    """Connected WooCommerce store credentials and status."""
    __tablename__ = "wc_stores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    store_name: Mapped[str] = mapped_column(String(255), nullable=False)
    store_url: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    consumer_key: Mapped[str] = mapped_column(String(512), nullable=False)
    consumer_secret: Mapped[str] = mapped_column(String(512), nullable=False)

    wc_store_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    wc_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    status: Mapped[StoreStatus] = mapped_column(
        Enum(StoreStatus, name="wc_store_status_enum"),
        default=StoreStatus.CONNECTED,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Webhook configuration
    webhook_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    webhooks_registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    owner: Mapped["RegisteredStudent"] = relationship(back_populates="wc_stores")  # type: ignore
    products: Mapped[list["WooCommerceProduct"]] = relationship(back_populates="store", cascade="all, delete-orphan")
    categories: Mapped[list["WooCommerceCategory"]] = relationship(back_populates="store", cascade="all, delete-orphan")
    tags: Mapped[list["WooCommerceTag"]] = relationship(back_populates="store", cascade="all, delete-orphan")
    customers: Mapped[list["WooCommerceCustomer"]] = relationship(back_populates="store", cascade="all, delete-orphan")
    orders: Mapped[list["WooCommerceOrder"]] = relationship(back_populates="store", cascade="all, delete-orphan")
    coupons: Mapped[list["WooCommerceCoupon"]] = relationship(back_populates="store", cascade="all, delete-orphan")
    alerts: Mapped[list["WooCommerceAlert"]] = relationship(back_populates="store", cascade="all, delete-orphan")
    sync_logs: Mapped[list["WooCommerceSyncLog"]] = relationship(back_populates="store", cascade="all, delete-orphan")
    settings: Mapped[list["WooCommerceSetting"]] = relationship(back_populates="store", cascade="all, delete-orphan")


class WooCommerceCategory(Base):
    """Product categories synced from WooCommerce."""
    __tablename__ = "wc_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wc_stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    wc_category_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wc_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    wc_parent_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    display: Mapped[str] = mapped_column(String(50), default="default")
    menu_order: Mapped[int] = mapped_column(Integer, default=0)
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    store: Mapped["WooCommerceStore"] = relationship(back_populates="categories")
    parent: Mapped["WooCommerceCategory | None"] = relationship(
        "WooCommerceCategory", remote_side="WooCommerceCategory.id", backref="children"
    )


class WooCommerceTag(Base):
    """Product tags synced from WooCommerce."""
    __tablename__ = "wc_tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wc_stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    wc_tag_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    store: Mapped["WooCommerceStore"] = relationship(back_populates="tags")


class WooCommerceProduct(Base):
    """Products synced from WooCommerce."""
    __tablename__ = "wc_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wc_stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    wc_product_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="simple", nullable=False)

    name: Mapped[str] = mapped_column(String(512), nullable=False)
    slug: Mapped[str] = mapped_column(String(512), nullable=True)
    permalink: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    sku: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True)

    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    regular_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    on_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    purchasable: Mapped[bool] = mapped_column(Boolean, default=True)

    featured_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    featured_image_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    gallery_image_urls: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Inventory
    manage_stock: Mapped[bool] = mapped_column(Boolean, default=False)
    stock_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reserved_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default=sa_text("0"))
    stock_status: Mapped[StockStatus] = mapped_column(
        Enum(StockStatus, name="wc_stock_status_enum"),
        default=StockStatus.IN_STOCK,
        nullable=False,
    )
    backorders: Mapped[str] = mapped_column(String(20), default="no")
    backorders_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    sold_individually: Mapped[bool] = mapped_column(Boolean, default=False)
    total_sales: Mapped[int] = mapped_column(Integer, default=0)

    # Shipping
    weight: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dimensions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    shipping_class: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shipping_required: Mapped[bool] = mapped_column(Boolean, default=True)

    # Tax
    tax_status: Mapped[str] = mapped_column(String(50), default="taxable")
    tax_class: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Attributes
    attributes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    default_attributes: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Categories & Tags (denormalized for query performance)
    category_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tag_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Ratings
    average_rating: Mapped[str] = mapped_column(String(10), default="0")
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    reviews_allowed: Mapped[bool] = mapped_column(Boolean, default=True)

    # Status
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(50), default="publish", nullable=False)

    # Raw data snapshot
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Sync tracking
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    store: Mapped["WooCommerceStore"] = relationship(back_populates="products")
    order_items: Mapped[list["WooCommerceOrderItem"]] = relationship(back_populates="product")


class WooCommerceOrder(Base):
    """Orders synced from WooCommerce."""
    __tablename__ = "wc_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wc_stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    wc_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    number: Mapped[str] = mapped_column(String(50), nullable=False)
    order_key: Mapped[str] = mapped_column(String(255), nullable=True)

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="wc_order_status_enum"),
        default=OrderStatus.PENDING,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(10), default="USD")

    # Customer
    customer_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    customer_ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    customer_user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    customer_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Addresses
    billing: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    shipping: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Payment
    payment_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payment_method_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_paid: Mapped[str | None] = mapped_column(String(50), nullable=True)
    date_completed: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Totals
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    discount_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    discount_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    shipping_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    shipping_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    cart_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    prices_include_tax: Mapped[bool] = mapped_column(Boolean, default=False)

    # Coupons, fees, shipping lines (denormalized for query performance)
    coupon_lines: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    fee_lines: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    shipping_lines: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tax_lines: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    refunds: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Raw data snapshot
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Sync tracking
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    store: Mapped["WooCommerceStore"] = relationship(back_populates="orders")
    items: Mapped[list["WooCommerceOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class WooCommerceOrderItem(Base):
    """Line items within WooCommerce orders."""
    __tablename__ = "wc_order_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wc_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    wc_order_item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    wc_product_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    name: Mapped[str] = mapped_column(String(512), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wc_products.id", ondelete="SET NULL"),
        nullable=True,
    )

    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    subtotal_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    meta_data: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    order: Mapped["WooCommerceOrder"] = relationship(back_populates="items")
    product: Mapped["WooCommerceProduct | None"] = relationship(back_populates="order_items")


class WooCommerceCustomer(Base):
    """Customers synced from WooCommerce."""
    __tablename__ = "wc_customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wc_stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    wc_customer_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="customer")
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    billing: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    shipping: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    orders_count: Mapped[int] = mapped_column(Integer, default=0)
    total_spent: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    meta_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    store: Mapped["WooCommerceStore"] = relationship(back_populates="customers")


class WooCommerceCoupon(Base):
    """Coupons synced from WooCommerce."""
    __tablename__ = "wc_coupons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wc_stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    wc_coupon_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    discount_type: Mapped[str] = mapped_column(String(50), default="fixed_cart", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_expires: Mapped[str | None] = mapped_column(String(50), nullable=True)

    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    individual_use: Mapped[bool] = mapped_column(Boolean, default=False)

    product_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    excluded_product_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    product_categories: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    excluded_product_categories: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_limit_per_user: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limit_usage_to_x_items: Mapped[int | None] = mapped_column(Integer, nullable=True)

    free_shipping: Mapped[bool] = mapped_column(Boolean, default=False)
    exclude_sale_items: Mapped[bool] = mapped_column(Boolean, default=False)

    minimum_amount: Mapped[str | None] = mapped_column(String(20), nullable=True)
    maximum_amount: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email_restrictions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    used_by: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    meta_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    store: Mapped["WooCommerceStore"] = relationship(back_populates="coupons")


class WooCommerceInventoryLog(Base):
    """Immutable audit trail for all inventory changes."""
    __tablename__ = "wc_inventory_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wc_stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wc_products.id", ondelete="SET NULL"),
        nullable=True,
    )

    wc_product_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)

    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    quantity_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity_change: Mapped[int | None] = mapped_column(Integer, nullable=True)

    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    source: Mapped[str] = mapped_column(String(50), default="manual")  # manual, sync, webhook, system
    performed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    store: Mapped["WooCommerceStore"] = relationship()
    product: Mapped["WooCommerceProduct | None"] = relationship()


class WooCommerceAlert(Base):
    """System alerts for inventory and sync events."""
    __tablename__ = "wc_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wc_stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    alert_type: Mapped[AlertType] = mapped_column(
        Enum(AlertType, name="wc_alert_type_enum"),
        nullable=False,
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, name="wc_alert_severity_enum"),
        default=AlertSeverity.WARNING,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # product, order, sync
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    email_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    meta_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    store: Mapped["WooCommerceStore"] = relationship(back_populates="alerts")


class WooCommerceSyncLog(Base):
    """Sync operation history for auditing and monitoring."""
    __tablename__ = "wc_sync_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wc_stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sync_type: Mapped[SyncType] = mapped_column(
        Enum(SyncType, name="wc_sync_type_enum"),
        nullable=False,
    )
    resource: Mapped[str] = mapped_column(String(50), nullable=False)  # products, orders, customers, etc.
    status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus, name="wc_sync_status_enum"),
        default=SyncStatus.PENDING,
        nullable=False,
    )

    total_items: Mapped[int] = mapped_column(Integer, default=0)
    created_items: Mapped[int] = mapped_column(Integer, default=0)
    updated_items: Mapped[int] = mapped_column(Integer, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, default=0)
    skipped_items: Mapped[int] = mapped_column(Integer, default=0)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    meta_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    store: Mapped["WooCommerceStore"] = relationship(back_populates="sync_logs")


class WooCommerceSetting(Base):
    """Store-specific configuration settings."""
    __tablename__ = "wc_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wc_stores.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Sync configuration
    auto_sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_interval_hours: Mapped[int] = mapped_column(Integer, default=6)
    sync_products: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_orders: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_customers: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_categories: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_coupons: Mapped[bool] = mapped_column(Boolean, default=True)

    # Alert configuration
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=10)
    low_stock_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_failure_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    email_alerts: Mapped[bool] = mapped_column(Boolean, default=False)
    alert_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Webhook configuration
    webhook_callback_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    webhook_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Data retention
    retention_days: Mapped[int] = mapped_column(Integer, default=90)
    archive_old_data: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    store: Mapped["WooCommerceStore"] = relationship(back_populates="settings")
