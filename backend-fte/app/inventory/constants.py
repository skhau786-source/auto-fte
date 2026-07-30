import enum
from decimal import Decimal


class TransactionType(str, enum.Enum):
    """
    Types of inventory transactions.
    
    This is the CANONICAL definition used by both SQLAlchemy (via Enum column type)
    and Pydantic schemas. Import this class, don't redefine it elsewhere.
    """
    ADJUSTMENT = "adjustment"
    SALE = "sale"
    PURCHASE = "purchase"
    RETURN = "return"
    TRANSFER = "transfer"
    SHOPIFY_SYNC = "shopify_sync"


class AllocationStrategy(str, enum.Enum):
    """Strategies for automatic warehouse allocation on order fulfillment."""
    DEFAULT_WAREHOUSE = "default_warehouse"
    HIGHEST_STOCK = "highest_stock"
    PRIORITY = "priority"
    ROUND_ROBIN = "round_robin"
    NEAREST_WAREHOUSE = "nearest_warehouse"
    MANUAL = "manual"


class WarehouseStatus(str, enum.Enum):
    """Status of a warehouse."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNDER_MAINTENANCE = "under_maintenance"
    CLOSED = "closed"


class TransferStatus(str, enum.Enum):
    """Status of a warehouse transfer."""
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    IN_TRANSIT = "in_transit"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    PARTIALLY_RECEIVED = "partially_received"


class ReservationStatus(str, enum.Enum):
    """
    Status of an inventory reservation.

    Lifecycle:
    PENDING -> ACTIVE -> COMMITTED
                      -> RELEASED
                      -> EXPIRED
                      -> CANCELLED
    """
    PENDING = "pending"
    ACTIVE = "active"
    COMMITTED = "committed"
    RELEASED = "released"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ReservationSource(str, enum.Enum):
    """Source of a reservation — identifies the originating system."""
    WOOCOMMERCE = "woocommerce"
    SHOPIFY = "shopify"
    MANUAL = "manual"
    TRANSFER = "transfer"
    AI_AGENT = "ai_agent"
    API = "api"


class InventoryAction(str, enum.Enum):
    """Actions logged in inventory_logs."""
    CREATED = "created"
    UPDATED = "updated"
    INVENTORY_ADJUSTED = "inventory_adjusted"
    SYNCED = "synced"
    LOW_STOCK_ALERT = "low_stock_alert"
    SHOPIFY_SYNC_FAILED = "shopify_sync_failed"
    WEBHOOK_UPDATED = "webhook_inventory_updated"
    BULK_IMPORTED = "bulk_imported"
    THRESHOLD_UPDATED = "threshold_updated"
    WAREHOUSE_CREATED = "warehouse_created"
    WAREHOUSE_UPDATED = "warehouse_updated"
    WAREHOUSE_ACTIVATED = "warehouse_activated"
    WAREHOUSE_DEACTIVATED = "warehouse_deactivated"
    TRANSFER_CREATED = "transfer_created"
    TRANSFER_APPROVED = "transfer_approved"
    TRANSFER_COMPLETED = "transfer_completed"
    TRANSFER_CANCELLED = "transfer_cancelled"
    STOCK_RESERVED = "stock_reserved"
    RESERVATION_RELEASED = "reservation_released"


class ProductStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DRAFT = "draft"


# Default thresholds
DEFAULT_LOW_STOCK_THRESHOLD: int = 10
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 100
DEFAULT_SYNC_INTERVAL_HOURS: int = 6
SYNC_RETRY_MINUTES: int = 5
