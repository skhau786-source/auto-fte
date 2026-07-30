"""
Domain-specific exceptions for the WooCommerce Integration Module.

Raised by the service layer; caught and converted to HTTP responses by the router.
Keeps business logic decoupled from HTTP concerns.
"""


class WooCommerceError(Exception):
    """Base exception for all WooCommerce domain errors."""

    def __init__(self, message: str, detail: dict | None = None):
        self.message = message
        self.detail = detail or {}
        super().__init__(self.message)


class StoreNotFoundError(WooCommerceError):
    """Raised when a store is not found."""

    def __init__(self, store_id: str | None = None):
        super().__init__(
            message="WooCommerce store not found",
            detail={"store_id": store_id},
        )


class StoreConnectionError(WooCommerceError):
    """Raised when WooCommerce API credentials are invalid."""

    def __init__(self, detail_msg: str = ""):
        super().__init__(
            message=f"Failed to connect to WooCommerce store: {detail_msg}",
            detail={"error": detail_msg},
        )


class StoreAlreadyExistsError(WooCommerceError):
    """Raised when a store with the same URL already exists."""

    def __init__(self, url: str):
        super().__init__(
            message=f"A store with URL '{url}' is already connected",
            detail={"url": url},
        )


class StoreInactiveError(WooCommerceError):
    """Raised when trying to operate on an inactive store."""

    def __init__(self, store_id: str):
        super().__init__(
            message=f"Store {store_id} is inactive. Reactivate it first.",
            detail={"store_id": store_id},
        )


class ProductNotFoundError(WooCommerceError):
    """Raised when a requested product does not exist."""

    def __init__(self, product_id: str):
        super().__init__(
            message=f"Product not found: {product_id}",
            detail={"product_id": product_id},
        )


class VariantNotFoundError(WooCommerceError):
    """Raised when a requested variant does not exist."""

    def __init__(self, variant_id: str):
        super().__init__(
            message=f"Variant not found: {variant_id}",
            detail={"variant_id": variant_id},
        )


class OrderNotFoundError(WooCommerceError):
    """Raised when a requested order does not exist."""

    def __init__(self, order_id: str):
        super().__init__(
            message=f"Order not found: {order_id}",
            detail={"order_id": order_id},
        )


class CustomerNotFoundError(WooCommerceError):
    """Raised when a requested customer does not exist."""

    def __init__(self, customer_id: str):
        super().__init__(
            message=f"Customer not found: {customer_id}",
            detail={"customer_id": customer_id},
        )


class CategoryNotFoundError(WooCommerceError):
    """Raised when a requested category does not exist."""

    def __init__(self, category_id: str):
        super().__init__(
            message=f"Category not found: {category_id}",
            detail={"category_id": category_id},
        )


class CouponNotFoundError(WooCommerceError):
    """Raised when a requested coupon does not exist."""

    def __init__(self, coupon_id: str):
        super().__init__(
            message=f"Coupon not found: {coupon_id}",
            detail={"coupon_id": coupon_id},
        )


class DuplicateSKUError(WooCommerceError):
    """Raised when a variant SKU already exists in the same store."""

    def __init__(self, sku: str):
        super().__init__(
            message=f"A variant with SKU '{sku}' already exists in this store",
            detail={"sku": sku},
        )


class InsufficientStockError(WooCommerceError):
    """Raised when attempting to reduce stock below zero."""

    def __init__(self, variant_id: str, current_quantity: int, requested_change: int):
        super().__init__(
            message=f"Insufficient stock. Current: {current_quantity}, requested change: {requested_change}",
            detail={
                "variant_id": variant_id,
                "current_quantity": current_quantity,
                "requested_change": requested_change,
            },
        )


class InvalidStoreOwnershipError(WooCommerceError):
    """Raised when a resource does not belong to the user's store."""

    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            message=f"{resource_type} {resource_id} does not belong to your store",
            detail={"resource_type": resource_type, "resource_id": resource_id},
        )


class WooCommerceAPIError(WooCommerceError):
    """Raised when the WooCommerce API returns an error."""

    def __init__(self, status_code: int, message: str):
        super().__init__(
            message=f"WooCommerce API error ({status_code}): {message}",
            detail={"status_code": status_code, "error": message},
        )


class WooCommerceRateLimitError(WooCommerceError):
    """Raised when WooCommerce API rate limit is exceeded."""

    def __init__(self, retry_after: int = 60):
        super().__init__(
            message=f"WooCommerce API rate limit exceeded. Retry after {retry_after}s",
            detail={"retry_after": retry_after},
        )


class SyncInProgressError(WooCommerceError):
    """Raised when a sync is already in progress for the same store/resource."""

    def __init__(self, store_id: str, resource: str):
        super().__init__(
            message=f"Sync already in progress for {resource} in store {store_id}",
            detail={"store_id": store_id, "resource": resource},
        )


class WebhookVerificationError(WooCommerceError):
    """Raised when webhook signature verification fails."""

    def __init__(self):
        super().__init__(
            message="Webhook signature verification failed",
            detail={},
        )


class WebhookNotFoundError(WooCommerceError):
    """Raised when a webhook delivery URL is not found."""

    def __init__(self, webhook_id: str):
        super().__init__(
            message=f"Webhook not found: {webhook_id}",
            detail={"webhook_id": webhook_id},
        )
