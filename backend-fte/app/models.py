import uuid
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum, func, Text, Integer, BigInteger, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.inventory.constants import (
    TransactionType, WarehouseStatus, TransferStatus,
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
# WAREHOUSE MANAGEMENT MODULES (Milestone 4)
# ═══════════════════════════════════════════════════════════════════


class Warehouse(Base):
    """
    Physical or virtual warehouse/storage location.
    Each warehouse belongs to a store and can hold inventory independently.
    """
    __tablename__ = "warehouses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Address
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)

    # Contact
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Capacity (in cubic meters or units)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Maximum storage capacity in units")
    capacity_unit: Mapped[str] = mapped_column(String(20), default="units", nullable=False)

    # Default warehouse flag (only one per store can be default)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Status
    status: Mapped[WarehouseStatus] = mapped_column(
        Enum(WarehouseStatus, name="warehouse_status_enum"),
        default=WarehouseStatus.ACTIVE,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    store: Mapped["Store"] = relationship()
    manager: Mapped["RegisteredStudent | None"] = relationship()
    inventory_items: Mapped[list["WarehouseInventory"]] = relationship(
        back_populates="warehouse", cascade="all, delete-orphan",
    )
    source_transfers: Mapped[list["WarehouseTransfer"]] = relationship(
        back_populates="source_warehouse_rel",
        foreign_keys="WarehouseTransfer.source_warehouse_id",
        cascade="all, delete-orphan",
    )
    dest_transfers: Mapped[list["WarehouseTransfer"]] = relationship(
        back_populates="destination_warehouse_rel",
        foreign_keys="WarehouseTransfer.destination_warehouse_id",
        cascade="all, delete-orphan",
    )


class WarehouseSettings(Base):
    """
    Per-store warehouse configuration settings.
    Controls how warehouses behave for inventory allocation, reservation, etc.
    One-to-one with Store — each store has exactly one settings record.
    """
    __tablename__ = "warehouse_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Which warehouse is the default
    default_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Behavior flags (B.1)
    auto_allocate_inventory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    multi_warehouse_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allocation_strategy: Mapped[str] = mapped_column(String(50), default="default_warehouse", nullable=False)
    allow_negative_stock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reserve_stock_on_order: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_release_cancelled_orders: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Priority ordering for PriorityWarehouseStrategy (Phase 4)
    allocation_priority: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    store: Mapped["Store"] = relationship()
    default_warehouse: Mapped["Warehouse | None"] = relationship()


class WarehouseInventory(Base):
    """
    Per-variant inventory tracking at each warehouse.
    This is the core multi-location inventory record.
    """
    __tablename__ = "warehouse_inventory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Stock breakdown
    available_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incoming_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    damaged_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Thresholds
    minimum_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    maximum_stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reorder_point: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Physical location within warehouse
    bin_location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shelf: Mapped[str | None] = mapped_column(String(100), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    warehouse: Mapped["Warehouse"] = relationship(back_populates="inventory_items")
    product: Mapped["Product | None"] = relationship()
    variant: Mapped["ProductVariant | None"] = relationship()

    # Unique constraint: one inventory record per variant per warehouse
    __table_args__ = (
        UniqueConstraint("warehouse_id", "variant_id", name="uq_warehouse_variant"),
    )


class WarehouseTransfer(Base):
    """
    Inventory transfer between warehouses.
    Tracks the full lifecycle: draft → pending → approved → in_transit → completed.
    """
    __tablename__ = "warehouse_transfers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    transfer_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)

    source_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    destination_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[TransferStatus] = mapped_column(
        Enum(TransferStatus, name="transfer_status_enum"),
        default=TransferStatus.DRAFT,
        nullable=False,
    )

    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="SET NULL"),
        nullable=True,
    )

    transfer_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    store: Mapped["Store"] = relationship()
    source_warehouse_rel: Mapped["Warehouse"] = relationship(
        back_populates="source_transfers",
        foreign_keys=[source_warehouse_id],
    )
    destination_warehouse_rel: Mapped["Warehouse"] = relationship(
        back_populates="dest_transfers",
        foreign_keys=[destination_warehouse_id],
    )
    requested_by: Mapped["RegisteredStudent | None"] = relationship(foreign_keys=[requested_by_id])
    approved_by: Mapped["RegisteredStudent | None"] = relationship(foreign_keys=[approved_by_id])
    items: Mapped[list["WarehouseTransferItem"]] = relationship(
        back_populates="transfer", cascade="all, delete-orphan",
    )


# ═══════════════════════════════════════════════════════════════════
# RESERVATION ENGINE (Phase 3)
# ═══════════════════════════════════════════════════════════════════


class InventoryReservation(Base):
    """
    Inventory reservation record.

    Tracks the full lifecycle: PENDING -> ACTIVE -> COMMITTED / RELEASED / EXPIRED / CANCELLED.
    Uses pessimistic locking (SELECT FOR UPDATE) to prevent double reservations.

    One reservation per (store, warehouse, variant, order) for positive tracking.
    """
    __tablename__ = "inventory_reservations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    inventory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouse_inventory.id", ondelete="SET NULL"),
        nullable=True,
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
    warehouse: Mapped["Warehouse"] = relationship()
    inventory: Mapped["WarehouseInventory | None"] = relationship()
    product: Mapped["Product | None"] = relationship()
    variant: Mapped["ProductVariant | None"] = relationship()

    # Ensure one active reservation per variant per order
    __table_args__ = (
        UniqueConstraint(
            "variant_id", "order_id", "warehouse_id",
            name="uq_reservation_variant_order_warehouse",
        ),
    )


class WarehouseTransferItem(Base):
    """Individual line items within a warehouse transfer."""
    __tablename__ = "warehouse_transfer_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transfer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouse_transfers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
    )

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    received_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    transfer: Mapped["WarehouseTransfer"] = relationship(back_populates="items")
    product: Mapped["Product | None"] = relationship()
    variant: Mapped["ProductVariant | None"] = relationship()
