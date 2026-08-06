"""
Domain-specific exceptions for the Inventory Management module.

These are raised by the service layer and caught by FastAPI exception handlers
or the router layer. They keep business logic decoupled from HTTP concerns.
"""


class InventoryError(Exception):
    """Base exception for all inventory domain errors."""

    def __init__(self, message: str, detail: dict | None = None):
        self.message = message
        self.detail = detail or {}
        super().__init__(self.message)


class ProductNotFoundError(InventoryError):
    """Raised when a requested product does not exist."""

    def __init__(self, product_id: str):
        super().__init__(
            message=f"Product not found: {product_id}",
            detail={"product_id": product_id},
        )


class VariantNotFoundError(InventoryError):
    """Raised when a requested variant does not exist."""

    def __init__(self, variant_id: str):
        super().__init__(
            message=f"Variant not found: {variant_id}",
            detail={"variant_id": variant_id},
        )


class CategoryNotFoundError(InventoryError):
    """Raised when a requested category does not exist."""

    def __init__(self, category_id: str):
        super().__init__(
            message=f"Category not found: {category_id}",
            detail={"category_id": category_id},
        )


class StoreNotFoundError(InventoryError):
    """Raised when no active Shopify store is found for the user."""

    def __init__(self, user_id: str | None = None):
        super().__init__(
            message="No active Shopify store found",
            detail={"user_id": user_id},
        )


class DuplicateSKUError(InventoryError):
    """Raised when a variant SKU already exists in the same store."""

    def __init__(self, sku: str):
        super().__init__(
            message=f"A variant with SKU '{sku}' already exists in this store",
            detail={"sku": sku},
        )


class DuplicateProductError(InventoryError):
    """Raised when a product with the same Shopify ID already exists."""

    def __init__(self, shopify_product_id: int):
        super().__init__(
            message=f"Product with Shopify ID {shopify_product_id} already exists",
            detail={"shopify_product_id": shopify_product_id},
        )


class InsufficientStockError(InventoryError):
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


class InvalidQuantityError(InventoryError):
    """Raised when a quantity value is invalid (e.g., zero change, negative values where not allowed)."""

    def __init__(self, field: str, reason: str):
        super().__init__(
            message=f"Invalid quantity for '{field}': {reason}",
            detail={"field": field, "reason": reason},
        )


class ShopifySyncError(InventoryError):
    """Raised when communication with the Shopify API fails."""

    def __init__(self, original_error: str):
        super().__init__(
            message=f"Failed to sync with Shopify: {original_error}",
            detail={"original_error": original_error},
        )


class InvalidStoreOwnershipError(InventoryError):
    """Raised when a resource does not belong to the user's store."""

    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            message=f"{resource_type} {resource_id} does not belong to your store",
            detail={"resource_type": resource_type, "resource_id": resource_id},
        )


class ReservationError(InventoryError):
    """Base exception for reservation engine domain errors."""


class ReservationNotFoundError(ReservationError):
    """Raised when a requested reservation does not exist."""

    def __init__(self, reservation_id: str):
        super().__init__(
            message=f"Reservation not found: {reservation_id}",
            detail={"reservation_id": reservation_id},
        )


class InsufficientStockForReservationError(ReservationError):
    """Raised when there is not enough stock to fulfill a reservation."""

    def __init__(self, variant_id: str, requested: int, available: int):
        super().__init__(
            message=f"Insufficient stock to reserve {requested} units for variant "
                    f"{variant_id} (available: {available})",
            detail={
                "variant_id": variant_id,
                "requested": requested,
                "available": available,
            },
        )


class InvalidReservationStateError(ReservationError):
    """Raised when a state transition is not allowed (e.g. committing a released reservation)."""

    def __init__(self, reservation_id: str, current_status: str, action: str):
        super().__init__(
            message=f"Cannot {action} reservation {reservation_id} in status '{current_status}'",
            detail={
                "reservation_id": reservation_id,
                "current_status": current_status,
                "action": action,
            },
        )


class DuplicateReservationError(ReservationError):
    """Raised when an active reservation already exists for the same variant/order."""

    def __init__(self, variant_id: str, order_id: str):
        super().__init__(
            message=f"An active reservation already exists for variant {variant_id} and order {order_id}",
            detail={"variant_id": variant_id, "order_id": order_id},
        )


class AllocationError(InventoryError):
    """Base exception for allocation engine domain errors."""


class AllocationFailedError(AllocationError):
    """Raised when allocation cannot be completed."""

    def __init__(self, reason: str):
        super().__init__(
            message=f"Allocation failed: {reason}",
            detail={"reason": reason},
        )


class InvalidAllocationStrategyError(AllocationError):
    """Raised when an unknown allocation strategy is requested."""

    def __init__(self, strategy_name: str):
        super().__init__(
            message=f"Unknown allocation strategy: {strategy_name}",
            detail={"strategy_name": strategy_name},
        )


class StoreSettingsNotFoundError(InventoryError):
    """Raised when store settings do not exist."""

    def __init__(self, store_id: str):
        super().__init__(
            message=f"Store settings not found for store {store_id}",
            detail={"store_id": store_id},
        )


class StoreSettingsValidationError(InventoryError):
    """Raised when store settings data is invalid."""

    def __init__(self, reason: str):
        super().__init__(
            message=f"Invalid store settings: {reason}",
            detail={"reason": reason},
        )
