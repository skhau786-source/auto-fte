"""
Constants and enumerations for the WooCommerce Integration Module.

All canonical enum values live here — import these, don't redefine them.
"""

import enum


class WooCommerceEndpoint(str, enum.Enum):
    """WooCommerce REST API v3 endpoint paths."""
    PRODUCTS = "/products"
    PRODUCTS_BY_ID = "/products/{id}"
    CATEGORIES = "/products/categories"
    CATEGORIES_BY_ID = "/products/categories/{id}"
    TAGS = "/products/tags"
    TAGS_BY_ID = "/products/tags/{id}"
    ATTRIBUTES = "/products/attributes"
    ATTRIBUTES_BY_ID = "/products/attributes/{id}"
    ORDERS = "/orders"
    ORDERS_BY_ID = "/orders/{id}"
    ORDER_NOTES = "/orders/{id}/notes"
    ORDER_REFUNDS = "/orders/{id}/refunds"
    CUSTOMERS = "/customers"
    CUSTOMERS_BY_ID = "/customers/{id}"
    COUPONS = "/coupons"
    COUPONS_BY_ID = "/coupons/{id}"
    REPORTS = "/reports"
    REPORTS_SALES = "/reports/sales"
    REPORTS_TOP_SELLERS = "/reports/top_sellers"
    WEBHOOKS = "/webhooks"
    WEBHOOKS_BY_ID = "/webhooks/{id}"
    SETTINGS = "/settings"
    SHIPPING_ZONES = "/shipping/zones"
    TAX_CLASSES = "/taxes/classes"
    VARIATIONS = "/products/{id}/variations"
    REVIEWS = "/products/reviews"


class SyncStatus(str, enum.Enum):
    """Status of a synchronization operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class SyncType(str, enum.Enum):
    """Types of data synchronization."""
    FULL = "full"
    INCREMENTAL = "incremental"
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    WEBHOOK = "webhook"


class OrderStatus(str, enum.Enum):
    """WooCommerce order statuses."""
    PENDING = "pending"
    PROCESSING = "processing"
    ON_HOLD = "on-hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    FAILED = "failed"
    TRASH = "trash"
    DRAFT = "draft"


class StockStatus(str, enum.Enum):
    """WooCommerce stock statuses."""
    IN_STOCK = "instock"
    OUT_OF_STOCK = "outofstock"
    ON_BACKORDER = "onbackorder"


class AlertType(str, enum.Enum):
    """Types of alerts the system can generate."""
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"
    SYNC_FAILED = "sync_failed"
    API_FAILURE = "api_failure"
    STORE_DISCONNECTED = "store_disconnected"
    ORDER_PAID = "order_paid"
    HIGH_VALUE_ORDER = "high_value_order"


class AlertSeverity(str, enum.Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class WebhookTopic(str, enum.Enum):
    """WooCommerce webhook topics."""
    PRODUCT_CREATED = "product.created"
    PRODUCT_UPDATED = "product.updated"
    PRODUCT_DELETED = "product.deleted"
    ORDER_CREATED = "order.created"
    ORDER_UPDATED = "order.updated"
    ORDER_DELETED = "order.deleted"
    CUSTOMER_CREATED = "customer.created"
    CUSTOMER_UPDATED = "customer.updated"
    CUSTOMER_DELETED = "customer.deleted"
    COUPON_CREATED = "coupon.created"
    COUPON_UPDATED = "coupon.updated"
    COUPON_DELETED = "coupon.deleted"
    CATEGORY_CREATED = "category.created"
    CATEGORY_UPDATED = "category.updated"
    CATEGORY_DELETED = "category.deleted"


class StoreStatus(str, enum.Enum):
    """WooCommerce store connection status."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    PENDING_VERIFICATION = "pending_verification"


# Configuration defaults
DEFAULT_SYNC_INTERVAL_HOURS: int = 6
DEFAULT_LOW_STOCK_THRESHOLD: int = 10
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 100
SYNC_RETRY_MINUTES: int = 5
MAX_RETRY_ATTEMPTS: int = 3
DEAD_LETTER_THRESHOLD_HOURS: int = 24

# WooCommerce API defaults
WC_API_VERSION: str = "wc/v3"
WP_API_VERSION: str = "wp/v2"
REQUEST_TIMEOUT_SECONDS: float = 30.0
PRODUCTS_PER_PAGE: int = 100
ORDERS_PER_PAGE: int = 100
CUSTOMERS_PER_PAGE: int = 100
