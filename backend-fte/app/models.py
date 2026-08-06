import uuid
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum, func, Text, Integer, BigInteger, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.inventory.constants import (
    TransactionType,
    ReservationStatus, ReservationSource,
)


class AuthProvider(str, enum.Enum):
    LOCAL = "local"
    GOOGLE = "google"


class LoginMethod(str, enum.Enum):
    LOCAL = "local"
    GOOGLE = "google"


class RegisteredStudent(Base):
    __tablename__ = "registered_students"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(150), nullable=True)

    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    auth_provider: Mapped[AuthProvider] = mapped_column(
        Enum(AuthProvider, name="auth_provider_enum"), default=AuthProvider.LOCAL, nullable=False
    )
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    login_records: Mapped[list["LoginUser"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )

    # Inventory relationships (Shopify)
    stores: Mapped[list["Store"]] = relationship(back_populates="owner", cascade="all, delete-orphan")

    # WooCommerce relationships
    wc_stores: Mapped[list["WooCommerceStore"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class LoginUser(Base):
    __tablename__ = "login_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    login_method: Mapped[LoginMethod] = mapped_column(Enum(LoginMethod, name="login_method_enum"), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logged_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student: Mapped["RegisteredStudent"] = relationship(back_populates="login_records")


# ═══════════════════════════════════════════════════════════════════
# INVENTORY MANAGEMENT MODULES
# ═══════════════════════════════════════════════════════════════════


class Store(Base):
    """
    Represents a connected Shopify store.
    Built by Team Member 2 — this is a scaffold that the inventory
    module depends on. Adjust columns to match the actual Store model.
    """
    __tablename__ = "stores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    shopify_domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    shopify_store_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    access_token: Mapped[str] = mapped_column(String(512), nullable=False)
    shopify_location_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    owner: Mapped["RegisteredStudent"] = relationship(back_populates="stores")
    products: Mapped[list["Product"]] = relationship(back_populates="store", cascade="all, delete-orphan")
    categories: Mapped[list["Category"]] = relationship(back_populates="store", cascade="all, delete-orphan")


class Category(Base):
    """Product categories. Supports hierarchical (parent/child) structure."""
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    shopify_category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    store: Mapped["Store"] = relationship(back_populates="categories")
    parent: Mapped["Category | None"] = relationship(
        "Category", remote_side="Category.id", backref="children"
    )
    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base):
    """Products synced from Shopify."""
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )

    shopify_product_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True, index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    featured_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Raw Shopify data snapshot (avoids schema drift from Shopify API changes)
    shopify_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    store: Mapped["Store"] = relationship(back_populates="products")
    category: Mapped["Category | None"] = relationship(back_populates="products")
    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan",
    )


class ProductVariant(Base):
    """Individual variants of a product. Each variant has its own inventory."""
    __tablename__ = "product_variants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    shopify_variant_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True, index=True)
    shopify_inventory_item_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True, index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    compare_at_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    inventory_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requires_shipping: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Per-variant low-stock threshold (overrides global default)
    low_stock_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True, default=10)

    # Raw Shopify data snapshot
    shopify_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="variants")
    transactions: Mapped[list["InventoryTransaction"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan",
    )
    logs: Mapped[list["InventoryLog"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan",
    )


class InventoryTransaction(Base):
    """
    Every inventory change is recorded here.
    Immutable audit trail — once created, rows should never be updated.
    """
    __tablename__ = "inventory_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type_enum"),
        nullable=False,
    )

    quantity_change: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_before: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_after: Mapped[int] = mapped_column(Integer, nullable=False)

    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    performed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="SET NULL"),
        nullable=True,
    )

    synced_to_shopify: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    variant: Mapped["ProductVariant"] = relationship(back_populates="transactions")
    performer: Mapped["RegisteredStudent | None"] = relationship()


class InventoryLog(Base):
    """
    Free-form activity log for inventory events.
    Stores JSON details so we can log arbitrary context per event.
    """
    __tablename__ = "inventory_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    performed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    variant: Mapped["ProductVariant"] = relationship(back_populates="logs")
    performer: Mapped["RegisteredStudent | None"] = relationship()


# ═══════════════════════════════════════════════════════════════════
# STORE CONFIGURATION (SaaS inventory platform)
# ═══════════════════════════════════════════════════════════════════


class StoreSettings(Base):
    """
    Per-store inventory & fulfillment configuration.

    Each store has exactly one settings record controlling allocation and
    reservation behavior (auto-allocate, reserve-on-order, negative stock,
    order cancellation).
    """
    __tablename__ = "store_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Behavior flags
    auto_allocate_inventory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allocation_strategy: Mapped[str] = mapped_column(String(50), default="default", nullable=False)
    allow_negative_stock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reserve_stock_on_order: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_release_cancelled_orders: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    store: Mapped["Store"] = relationship()


# ═══════════════════════════════════════════════════════════════════
# RESERVATION ENGINE (Phase 3)
# ═══════════════════════════════════════════════════════════════════


class InventoryReservation(Base):
    """
    Inventory reservation record.

    Tracks the full lifecycle: PENDING -> ACTIVE -> COMMITTED / RELEASED / EXPIRED / CANCELLED.
    Uses pessimistic locking (SELECT FOR UPDATE) on the variant to prevent
    double reservations.

    One reservation per (store, variant, order) for positive tracking.
    """
    __tablename__ = "inventory_reservations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Order tracking
    order_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    order_source: Mapped[ReservationSource] = mapped_column(
        Enum(ReservationSource, name="reservation_source_enum"),
        nullable=False,
        default=ReservationSource.MANUAL,
    )

    # Quantity and status
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus, name="reservation_status_enum"),
        nullable=False,
        default=ReservationStatus.ACTIVE,
    )

    # Expiration
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Lifecycle timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Flexible metadata (source order payload, etc.)
    # NOTE: Named 'meta_data' to avoid conflict with SQLAlchemy's reserved 'metadata' attribute
    meta_data: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    store: Mapped["Store"] = relationship()
    product: Mapped["Product | None"] = relationship()
    variant: Mapped["ProductVariant | None"] = relationship()

    # Ensure one active reservation per variant per order
    __table_args__ = (
        UniqueConstraint(
            "variant_id", "order_id",
            name="uq_reservation_variant_order",
        ),
    )

