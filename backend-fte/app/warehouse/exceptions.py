"""
Domain-specific exceptions for the Warehouse Management module.

Reuses the base InventoryError pattern from the Inventory module.
Caught by the router layer and converted to HTTP responses with
structured error details.
"""

from app.inventory.exceptions import InventoryError


class WarehouseError(InventoryError):
    """Base exception for all warehouse domain errors."""
    pass


class WarehouseNotFoundError(WarehouseError):
    """Raised when a warehouse is not found."""

    def __init__(self, warehouse_id: str):
        super().__init__(
            message=f"Warehouse not found: {warehouse_id}",
            detail={"warehouse_id": warehouse_id},
        )


class WarehouseAlreadyExistsError(WarehouseError):
    """Raised when a warehouse with the same code already exists."""

    def __init__(self, code: str):
        super().__init__(
            message=f"A warehouse with code '{code}' already exists",
            detail={"code": code},
        )


class WarehouseInactiveError(WarehouseError):
    """Raised when trying to operate on an inactive warehouse."""

    def __init__(self, warehouse_id: str):
        super().__init__(
            message=f"Warehouse {warehouse_id} is inactive. Activate it first.",
            detail={"warehouse_id": warehouse_id},
        )


class WarehouseAtCapacityError(WarehouseError):
    """Raised when a warehouse has reached its maximum capacity."""

    def __init__(self, warehouse_id: str, capacity: int, current_usage: int):
        super().__init__(
            message=f"Warehouse at capacity: {current_usage}/{capacity} units used",
            detail={
                "warehouse_id": warehouse_id,
                "capacity": capacity,
                "current_usage": current_usage,
            },
        )


class WarehouseInventoryNotFoundError(WarehouseError):
    """Raised when no inventory record is found for a variant at a warehouse."""

    def __init__(self, warehouse_id: str, variant_id: str):
        super().__init__(
            message=f"Inventory not found for variant {variant_id} at warehouse {warehouse_id}",
            detail={"warehouse_id": warehouse_id, "variant_id": variant_id},
        )


class TransferNotFoundError(WarehouseError):
    """Raised when a warehouse transfer is not found."""

    def __init__(self, transfer_id: str):
        super().__init__(
            message=f"Warehouse transfer not found: {transfer_id}",
            detail={"transfer_id": transfer_id},
        )


class InvalidTransferStateError(WarehouseError):
    """Raised when an operation is invalid for the current transfer state."""

    def __init__(self, transfer_id: str, current_status: str, required_status: str):
        super().__init__(
            message=f"Transfer {transfer_id} has status '{current_status}', "
                    f"expected '{required_status}'",
            detail={
                "transfer_id": transfer_id,
                "current_status": current_status,
                "required_status": required_status,
            },
        )


class SameWarehouseTransferError(WarehouseError):
    """Raised when source and destination warehouses are the same."""

    def __init__(self, warehouse_id: str):
        super().__init__(
            message=f"Source and destination warehouses cannot be the same ({warehouse_id})",
            detail={"warehouse_id": warehouse_id},
        )


class InsufficientWarehouseStockError(WarehouseError):
    """Raised when a warehouse doesn't have enough stock for a transfer/reservation."""

    def __init__(self, warehouse_id: str, variant_id: str, available: int, requested: int):
        super().__init__(
            message=f"Insufficient stock in warehouse {warehouse_id}: "
                    f"{available} available, {requested} requested",
            detail={
                "warehouse_id": warehouse_id,
                "variant_id": variant_id,
                "available": available,
                "requested": requested,
            },
        )


class ReservationNotFoundError(WarehouseError):
    """Raised when a stock reservation is not found."""

    def __init__(self, reservation_id: str):
        super().__init__(
            message=f"Stock reservation not found: {reservation_id}",
            detail={"reservation_id": reservation_id},
        )


class WarehouseSettingsNotFoundError(WarehouseError):
    """Raised when warehouse settings are not found for a store."""

    def __init__(self, store_id: str):
        super().__init__(
            message=f"Warehouse settings not found for store '{store_id}'",
            detail={"store_id": store_id},
        )


class WarehouseSettingsValidationError(WarehouseError):
    """Raised when warehouse settings fail validation."""

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message=message, detail=detail or {})


class ReservationError(WarehouseError):
    """Base exception for reservation domain errors."""
    pass


class ReservationNotFoundError(ReservationError):
    """Raised when a reservation is not found."""

    def __init__(self, reservation_id: str):
        super().__init__(
            message=f"Reservation not found: {reservation_id}",
            detail={"reservation_id": reservation_id},
        )


class InsufficientStockForReservationError(ReservationError):
    """Raised when there is not enough available stock to reserve."""

    def __init__(self, variant_id: str, warehouse_id: str, available: int, requested: int):
        super().__init__(
            message=f"Insufficient available stock to reserve: "
                    f"{available} available, {requested} requested",
            detail={
                "variant_id": variant_id,
                "warehouse_id": warehouse_id,
                "available": available,
                "requested": requested,
            },
        )


class InvalidReservationStateError(ReservationError):
    """Raised when an operation is invalid for the current reservation state."""

    def __init__(self, reservation_id: str, current_status: str, allowed_statuses: list[str]):
        super().__init__(
            message=f"Reservation {reservation_id} has status '{current_status}', "
                    f"expected one of: {', '.join(allowed_statuses)}",
            detail={
                "reservation_id": reservation_id,
                "current_status": current_status,
                "allowed_statuses": allowed_statuses,
            },
        )


class DuplicateReservationError(ReservationError):
    """Raised when a duplicate reservation is attempted for the same variant/order."""

    def __init__(self, variant_id: str, order_id: str, warehouse_id: str):
        super().__init__(
            message=f"Active reservation already exists for variant {variant_id}, "
                    f"order {order_id}, warehouse {warehouse_id}",
            detail={
                "variant_id": variant_id,
                "order_id": order_id,
                "warehouse_id": warehouse_id,
            },
        )


# ═══════════════════════════════════════════════════════════════════
# ALLOCATION ENGINE EXCEPTIONS (Phase 4)
# ═══════════════════════════════════════════════════════════════════

class AllocationError(WarehouseError):
    """Base exception for allocation domain errors."""
    pass


class AllocationFailedError(AllocationError):
    """Raised when allocation cannot fulfill the requested quantity."""

    def __init__(self, variant_id: str, requested: int, fulfilled: int):
        super().__init__(
            message=f"Allocation failed: {requested} requested, only {fulfilled} available",
            detail={
                "variant_id": variant_id,
                "requested": requested,
                "fulfilled": fulfilled,
            },
        )


class InvalidAllocationStrategyError(AllocationError):
    """Raised when an invalid strategy name is requested."""

    def __init__(self, strategy: str):
        super().__init__(
            message=f"Invalid allocation strategy: '{strategy}'",
            detail={"strategy": strategy},
        )


class AllocationHistoryNotFoundError(AllocationError):
    """Raised when allocation history record is not found."""

    def __init__(self, allocation_id: str):
        super().__init__(
            message=f"Allocation record not found: {allocation_id}",
            detail={"allocation_id": allocation_id},
        )
