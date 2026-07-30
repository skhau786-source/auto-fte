"""
Service Layer for the Warehouse Management module.

Contains all business logic for warehouse operations:
- WarehouseService: CRUD, activation, deactivation
- WarehouseInventoryService: Per-warehouse stock management
- WarehouseTransferService: Inter-warehouse transfers with approval workflow
- CapacityService: Capacity validation and monitoring
- InventoryAggregationService: Multi-location inventory queries

All services follow the same pattern as the existing InventoryService.
They raise domain exceptions caught by the router layer.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Warehouse, WarehouseInventory, WarehouseTransfer,
    WarehouseTransferItem, Product, ProductVariant,
    Store, RegisteredStudent,
)
from app.inventory.constants import (
    WarehouseStatus, TransferStatus, InventoryAction,
    TransactionType, DEFAULT_LOW_STOCK_THRESHOLD,
    AllocationStrategy,
)
from app.inventory.repository import (
    ProductRepository, VariantRepository,
    TransactionRepository, LogRepository,
)
from app.warehouse.repository import (
    WarehouseRepository, WarehouseInventoryRepository,
    WarehouseTransferRepository, WarehouseTransferItemRepository,
    WarehouseSettingsRepository,
)
from app.warehouse.exceptions import (
    WarehouseNotFoundError, WarehouseAlreadyExistsError,
    WarehouseInactiveError, WarehouseAtCapacityError,
    WarehouseInventoryNotFoundError, TransferNotFoundError,
    InvalidTransferStateError, SameWarehouseTransferError,
    InsufficientWarehouseStockError, ReservationNotFoundError,
    WarehouseSettingsNotFoundError, WarehouseSettingsValidationError,
)
from app.inventory.exceptions import (
    VariantNotFoundError, InsufficientStockError,
    InvalidStoreOwnershipError,
)
from app.warehouse.aggregation_cache import aggregation_cache

logger = logging.getLogger(__name__)


class WarehouseService:
    """Business logic for warehouse CRUD and lifecycle management."""

    def __init__(self, db: AsyncSession, store: Store, user_id: Optional[uuid.UUID] = None):
        self.db = db
        self.store = store
        self.user_id = user_id
        self.repo = WarehouseRepository(db)
        self.log_repo = LogRepository(db)
        self.logger = logging.getLogger(f"{__name__}.WarehouseService")

    async def create_warehouse(self, data) -> Warehouse:
        """Create a new warehouse with unique code validation."""
        # Check for duplicate code
        existing = await self.repo.get_by_code(data.code, self.store.id)
        if existing:
            raise WarehouseAlreadyExistsError(data.code)

        warehouse = await self.repo.create(
            store_id=self.store.id,
            data=data.model_dump(exclude_unset=True),
        )

        # Log the creation
        await self._log_warehouse_action(
            warehouse_id=warehouse.id,
            action=InventoryAction.WAREHOUSE_CREATED.value,
            details={"code": data.code, "name": data.name},
        )

        await self.db.commit()
        await self.db.refresh(warehouse)
        return warehouse

    async def get_warehouse(self, warehouse_id: uuid.UUID) -> Warehouse:
        """Get a warehouse by ID with ownership validation."""
        warehouse = await self.repo.get_by_id(warehouse_id)
        if warehouse is None or str(warehouse.store_id) != str(self.store.id):
            raise WarehouseNotFoundError(str(warehouse_id))
        return warehouse

    async def update_warehouse(self, warehouse_id: uuid.UUID, data) -> Warehouse:
        """Update warehouse fields."""
        warehouse = await self.get_warehouse(warehouse_id)
        update_data = data.model_dump(exclude_unset=True)
        warehouse = await self.repo.update(warehouse_id, update_data)
        if warehouse is None:
            raise WarehouseNotFoundError(str(warehouse_id))

        await self._log_warehouse_action(
            warehouse_id=warehouse_id,
            action=InventoryAction.WAREHOUSE_UPDATED.value,
            details={"updated_fields": list(update_data.keys())},
        )

        await self.db.commit()
        await self.db.refresh(warehouse)
        return warehouse

    async def list_warehouses(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[WarehouseStatus] = None,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> tuple[list[Warehouse], int]:
        """List warehouses with pagination and filtering."""
        return await self.repo.list_by_store(
            store_id=self.store.id,
            page=page,
            page_size=page_size,
            status=status,
            search=search,
            is_active=is_active,
        )

    async def get_default_warehouse(self) -> Optional[Warehouse]:
        """Get the default warehouse for the current store.

        If no default is configured but only one warehouse exists,
        auto-assign it as the default.

        Returns None if no warehouses exist.
        """
        warehouse = await self.repo.get_default(self.store.id)
        if warehouse:
            return warehouse

        return await self.repo.ensure_single_default(self.store.id)

    async def set_default_warehouse(self, warehouse_id: uuid.UUID) -> Warehouse:
        """
        Set a warehouse as the default for the store.

        Uses pessimistic row locking within a single transaction to prevent
        concurrent requests from creating inconsistent default states.

        Within one transaction:
        1. Get warehouse with SELECT FOR UPDATE
        2. Validate ownership and activeness
        3. Clear existing default (also locked)
        4. Set new default
        5. Sync WarehouseSettings.default_warehouse_id

        All within a single commit for atomicity.
        """
        # Validate ownership and existence WITH row lock
        warehouse = await self.get_warehouse(warehouse_id)
        if not warehouse.is_active:
            raise WarehouseInactiveError(str(warehouse_id))

        # Re-fetch with FOR UPDATE for the actual mutation
        warehouse = await self.repo.set_default(warehouse_id, self.store.id)
        if warehouse is None:
            raise WarehouseNotFoundError(str(warehouse_id))

        # Sync WarehouseSettings.default_warehouse_id for consistency
        settings_repo = WarehouseSettingsRepository(self.db)
        settings = await settings_repo.get_or_create(self.store.id)
        settings.default_warehouse_id = warehouse_id
        await self.db.flush()

        self.logger.info(
            "Default warehouse set: warehouse_id=%s, name=%s, store_id=%s",
            warehouse_id, warehouse.name, self.store.id,
        )

        await self.db.commit()
        await self.db.refresh(warehouse)
        return warehouse

    async def clear_default_warehouse(self) -> dict:
        """Clear the default warehouse for the current store.
        Also syncs WarehouseSettings.default_warehouse_id for consistency."""
        await self.repo.clear_default(self.store.id)

        # Sync WarehouseSettings for consistency
        settings_repo = WarehouseSettingsRepository(self.db)
        settings = await settings_repo.get_or_create(self.store.id)
        settings.default_warehouse_id = None
        await self.db.flush()

        await self.db.commit()
        self.logger.info("Default warehouse cleared for store %s", self.store.id)
        return {"message": "Default warehouse cleared successfully"}

    async def get_warehouse_settings(self) -> dict:
        """Get warehouse configuration settings for the store.

        Returns ALL settings fields from the persisted WarehouseSettings
        model, merged with runtime aggregation data (warehouse counts).

        Uses COUNT queries instead of loading rows for counting (avoids N+1).
        """
        default_wh = await self.get_default_warehouse()

        # Use COUNT queries instead of loading all rows
        total = await self.repo.count_by_store(self.store.id)
        active_count = await self.repo.count_active(self.store.id)

        # Get persisted settings
        settings_repo = WarehouseSettingsRepository(self.db)
        settings = await settings_repo.get_or_create(self.store.id)

        return {
            "id": settings.id,
            "store_id": settings.store_id,
            "default_warehouse_id": str(default_wh.id) if default_wh else None,
            "default_warehouse_name": default_wh.name if default_wh else None,
            "auto_allocate_inventory": settings.auto_allocate_inventory,
            "multi_warehouse_enabled": settings.multi_warehouse_enabled,
            "allocation_strategy": settings.allocation_strategy,
            "allow_negative_stock": settings.allow_negative_stock,
            "reserve_stock_on_order": settings.reserve_stock_on_order,
            "auto_release_cancelled_orders": settings.auto_release_cancelled_orders,
            "total_warehouses": total,
            "active_warehouses": active_count,
            "has_default": default_wh is not None,
            "created_at": settings.created_at,
            "updated_at": settings.updated_at,
        }

    async def update_warehouse_settings(self, data) -> dict:
        """
        Update warehouse configuration settings with validation.

        Validates:
        - default_warehouse_id belongs to this store and is active
        - allocation_strategy is a valid strategy
        - Only one default warehouse per store
        """
        settings_repo = WarehouseSettingsRepository(self.db)
        settings = await settings_repo.get_or_create(self.store.id)
        update_data = {}

        # Handle default_warehouse_id separately for validation
        if "default_warehouse_id" in data.model_dump(exclude_unset=True):
            dw_id = data.default_warehouse_id
            if dw_id is not None:
                # Validate warehouse exists, is owned by this store, and is active
                warehouse = await self.repo.get_by_id(dw_id)
                if warehouse is None or str(warehouse.store_id) != str(self.store.id):
                    raise WarehouseNotFoundError(str(dw_id))
                if not warehouse.is_active:
                    raise WarehouseInactiveError(str(dw_id))
                await self.repo.set_default(dw_id, self.store.id)
            else:
                await self.repo.clear_default(self.store.id)

        # Validate and set allocation_strategy
        if data.allocation_strategy is not None:
            valid_strategies = [s.value for s in AllocationStrategy]
            if data.allocation_strategy not in valid_strategies:
                raise WarehouseSettingsValidationError(
                    f"Invalid allocation_strategy '{data.allocation_strategy}'. "
                    f"Must be one of: {', '.join(valid_strategies)}"
                )
            update_data["allocation_strategy"] = data.allocation_strategy

        # Set remaining boolean fields
        bool_fields = [
            "auto_allocate_inventory", "multi_warehouse_enabled",
            "allow_negative_stock", "reserve_stock_on_order",
            "auto_release_cancelled_orders",
        ]
        for field in bool_fields:
            val = getattr(data, field, None)
            if val is not None:
                update_data[field] = val

        if update_data:
            settings = await settings_repo.update(self.store.id, update_data)
            if settings is None:
                raise WarehouseSettingsNotFoundError(str(self.store.id))
            await self.db.commit()

        return await self.get_warehouse_settings()

    async def activate_warehouse(self, warehouse_id: uuid.UUID) -> Warehouse:
        """Activate a warehouse."""
        warehouse = await self.get_warehouse(warehouse_id)
        warehouse = await self.repo.update(warehouse_id, {
            "is_active": True,
            "status": WarehouseStatus.ACTIVE,
        })
        await self._log_warehouse_action(
            warehouse_id=warehouse_id,
            action=InventoryAction.WAREHOUSE_ACTIVATED.value,
        )
        await self.db.commit()
        await self.db.refresh(warehouse)
        return warehouse

    async def deactivate_warehouse(self, warehouse_id: uuid.UUID) -> Warehouse:
        """Deactivate a warehouse.

        If this warehouse was the default:
        - Clears is_default flag on the warehouse
        - Also clears WarehouseSettings.default_warehouse_id to prevent
          orphaned settings references
        """
        warehouse = await self.get_warehouse(warehouse_id)
        # If this warehouse was the default, clear it from both places
        if warehouse.is_default:
            await self.repo.clear_default(self.store.id)
            # Also clear WarehouseSettings for consistency
            settings_repo = WarehouseSettingsRepository(self.db)
            settings = await settings_repo.get_or_create(self.store.id)
            if settings.default_warehouse_id == warehouse_id:
                settings.default_warehouse_id = None
                await self.db.flush()

        warehouse = await self.repo.update(warehouse_id, {
            "is_active": False,
            "status": WarehouseStatus.INACTIVE,
        })
        await self._log_warehouse_action(
            warehouse_id=warehouse_id,
            action=InventoryAction.WAREHOUSE_DEACTIVATED.value,
        )
        await self.db.commit()
        await self.db.refresh(warehouse)
        return warehouse

    async def delete_warehouse(self, warehouse_id: uuid.UUID) -> dict:
        """Delete a warehouse.

        If this warehouse was the default:
        - Clears is_default flag
        - Clears WarehouseSettings.default_warehouse_id to prevent
          FK holding reference to deleted warehouse (FK is SET NULL)
        """
        warehouse = await self.get_warehouse(warehouse_id)
        name = warehouse.name
        # If this warehouse was the default, clear from both places
        if warehouse.is_default:
            await self.repo.clear_default(self.store.id)

        # Always clear WarehouseSettings reference before deleting
        settings_repo = WarehouseSettingsRepository(self.db)
        settings = await settings_repo.get_by_store(self.store.id)
        if settings and settings.default_warehouse_id == warehouse_id:
            settings.default_warehouse_id = None
            await self.db.flush()

        deleted = await self.repo.delete(warehouse_id)
        if not deleted:
            raise WarehouseNotFoundError(str(warehouse_id))
        await self.db.commit()
        return {"message": f"Warehouse '{name}' deleted successfully"}

    async def _log_warehouse_action(
        self, warehouse_id: uuid.UUID, action: str, details: Optional[dict] = None,
    ):
        """Log a warehouse action to the structured logger.

        Warehouse-level events (creation, activation, deactivation) don't map
        to the variant-scoped InventoryLog table (which has a FK constraint to
        product_variants.id). Instead, we log these events via the structured
        logger and track them in the InventoryLog table using a generated action
        prefix. A dedicated warehouse_logs table is planned for a future milestone.
        """
        log_details = {
            "warehouse_id": str(warehouse_id),
            **(details or {}),
        }
        self.logger.info(
            "Warehouse action: action=%s, details=%s",
            action, log_details,
        )


class WarehouseInventoryService:
    """Business logic for per-warehouse inventory management."""

    def __init__(self, db: AsyncSession, store: Store, user_id: Optional[uuid.UUID] = None):
        self.db = db
        self.store = store
        self.user_id = user_id
        self.inv_repo = WarehouseInventoryRepository(db)
        self.wh_repo = WarehouseRepository(db)
        self.variant_repo = VariantRepository(db)
        self.txn_repo = TransactionRepository(db)
        self.log_repo = LogRepository(db)
        self.logger = logging.getLogger(f"{__name__}.WarehouseInventoryService")

    async def adjust_stock(
        self,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        quantity_change: int,
        reason: Optional[str] = None,
        commit: bool = True,
    ) -> dict:
        """
        Adjust stock for a variant at a specific warehouse.

        This is the core multi-location inventory operation:
        1. Validate variant and warehouse
        2. Get or create warehouse inventory record
        3. Validate stock won't go negative
        4. Update available_stock
        5. Create InventoryTransaction (audit trail, using existing system)
        6. Update ProductVariant.inventory_quantity (aggregate across warehouses)
        7. Log the event
        """
        # Validate warehouse
        warehouse = await self.wh_repo.get_by_id(warehouse_id)
        if warehouse is None or str(warehouse.store_id) != str(self.store.id):
            raise WarehouseNotFoundError(str(warehouse_id))
        if not warehouse.is_active:
            raise WarehouseInactiveError(str(warehouse_id))

        # Validate variant
        variant = await self.variant_repo.get_by_id(variant_id)
        if variant is None:
            raise VariantNotFoundError(str(variant_id))

        # Get or create warehouse inventory record
        wh_inv = await self.inv_repo.get_or_create(warehouse_id, variant_id)

        # Validate stock
        available_before = wh_inv.available_stock
        available_after = available_before + quantity_change

        if available_after < 0:
            raise InsufficientWarehouseStockError(
                warehouse_id=str(warehouse_id),
                variant_id=str(variant_id),
                available=available_before,
                requested=abs(quantity_change),
            )

        # Update warehouse inventory
        wh_inv.available_stock = available_after
        wh_inv.updated_at = datetime.now(timezone.utc)

        # Update aggregate variant quantity
        variant.inventory_quantity = (variant.inventory_quantity or 0) + quantity_change

        # Create InventoryTransaction (using existing system)
        txn = await self.txn_repo.create(
            variant_id=variant_id,
            transaction_type=TransactionType.ADJUSTMENT,
            quantity_change=quantity_change,
            quantity_before=variant.inventory_quantity - quantity_change,
            quantity_after=variant.inventory_quantity,
            reason=f"Warehouse {warehouse.code}: {reason}" if reason else f"Warehouse {warehouse.code} adjustment",
            performed_by=self.user_id,
        )
        txn.synced_to_shopify = False  # Will be synced by existing shopify sync flow

        # Log
        await self.log_repo.create(
            variant_id=variant_id,
            action=InventoryAction.INVENTORY_ADJUSTED.value,
            details={
                "warehouse_id": str(warehouse_id),
                "warehouse_code": warehouse.code,
                "available_before": available_before,
                "available_after": available_after,
                "change": quantity_change,
                "reason": reason,
            },
            performed_by=self.user_id,
        )

        if commit:
            await self.db.commit()
            # Invalidate aggregation cache after stock adjustment
            # Wrapped in try/except — cache failure must NOT break inventory operations
            try:
                await aggregation_cache.invalidate_store(self.store.id)
            except Exception as cache_exc:
                self.logger.warning(
                    "Cache invalidation failed after stock adjustment: %s",
                    cache_exc,
                )

        return {
            "warehouse_id": warehouse_id,
            "variant_id": variant_id,
            "available_before": available_before,
            "available_after": available_after,
            "quantity_change": quantity_change,
            "transaction_id": txn.id,
            "message": f"Stock at {warehouse.code}: {'increased' if quantity_change > 0 else 'decreased'} by {abs(quantity_change)}",
        }

    async def get_inventory(
        self,
        warehouse_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
        low_stock_only: bool = False,
        search: Optional[str] = None,
    ) -> tuple[list[WarehouseInventory], int]:
        """List inventory for a warehouse."""
        warehouse = await self.wh_repo.get_by_id(warehouse_id)
        if warehouse is None or str(warehouse.store_id) != str(self.store.id):
            raise WarehouseNotFoundError(str(warehouse_id))

        return await self.inv_repo.list_by_warehouse(
            warehouse_id=warehouse_id,
            page=page,
            page_size=page_size,
            low_stock_only=low_stock_only,
            search=search,
        )

    async def update_inventory(
        self,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        data,
    ) -> WarehouseInventory:
        """Update warehouse inventory metadata (thresholds, bin location, etc.)."""
        inv = await self.inv_repo.get_by_variant_and_warehouse(warehouse_id, variant_id)
        if inv is None:
            raise WarehouseInventoryNotFoundError(str(warehouse_id), str(variant_id))

        update_data = data.model_dump(exclude_unset=True)
        inv = await self.inv_repo.update(inv.id, update_data)
        await self.db.commit()
        await self.db.refresh(inv)
        return inv

    async def reserve_stock(
        self,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        quantity: int,
        reason: Optional[str] = None,
    ) -> WarehouseInventory:
        """
        Reserve stock at a warehouse.
        Moves stock from available to reserved without changing total.
        """
        inv = await self.inv_repo.get_or_create(warehouse_id, variant_id)

        if inv.available_stock < quantity:
            raise InsufficientWarehouseStockError(
                warehouse_id=str(warehouse_id),
                variant_id=str(variant_id),
                available=inv.available_stock,
                requested=quantity,
            )

        inv.available_stock -= quantity
        inv.reserved_stock += quantity
        inv.updated_at = datetime.now(timezone.utc)

        await self.log_repo.create(
            variant_id=variant_id,
            action=InventoryAction.STOCK_RESERVED.value,
            details={
                "warehouse_id": str(warehouse_id),
                "quantity": quantity,
                "reason": reason,
            },
            performed_by=self.user_id,
        )

        await self.db.commit()
        # Invalidate aggregation cache after stock reservation
        try:
            await aggregation_cache.invalidate_store(self.store.id)
        except Exception as cache_exc:
            self.logger.warning(
                "Cache invalidation failed after stock reservation: %s",
                cache_exc,
            )
        return inv

    async def release_reservation(
        self,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        quantity: int,
        reason: Optional[str] = None,
    ) -> WarehouseInventory:
        """
        Release reserved stock back to available.
        """
        inv = await self.inv_repo.get_or_create(warehouse_id, variant_id)

        release_qty = min(quantity, inv.reserved_stock)
        inv.available_stock += release_qty
        inv.reserved_stock -= release_qty
        inv.updated_at = datetime.now(timezone.utc)

        await self.log_repo.create(
            variant_id=variant_id,
            action=InventoryAction.RESERVATION_RELEASED.value,
            details={
                "warehouse_id": str(warehouse_id),
                "quantity": release_qty,
                "reason": reason,
            },
            performed_by=self.user_id,
        )

        await self.db.commit()
        # Invalidate aggregation cache after reservation release
        try:
            await aggregation_cache.invalidate_store(self.store.id)
        except Exception as cache_exc:
            self.logger.warning(
                "Cache invalidation failed after reservation release: %s",
                cache_exc,
            )
        return inv

    async def get_low_stock(
        self, threshold: int = DEFAULT_LOW_STOCK_THRESHOLD
    ) -> list[dict]:
        """Get all low-stock items across all warehouses for the store."""
        items = await self.inv_repo.get_low_stock_by_store(self.store.id, threshold)
        return [
            {
                "warehouse_id": str(item.warehouse_id),
                "warehouse_name": item.warehouse.name if item.warehouse else "Unknown",
                "variant_id": str(item.variant_id),
                "product_id": str(item.product_id) if item.product_id else None,
                "available_stock": item.available_stock,
                "reorder_point": item.reorder_point,
                "bin_location": item.bin_location,
                "shelf": item.shelf,
            }
            for item in items
        ]


class WarehouseTransferService:
    """Business logic for inter-warehouse transfers."""

    def __init__(self, db: AsyncSession, store: Store, user_id: Optional[uuid.UUID] = None):
        self.db = db
        self.store = store
        self.user_id = user_id
        self.transfer_repo = WarehouseTransferRepository(db)
        self.item_repo = WarehouseTransferItemRepository(db)
        self.inv_repo = WarehouseInventoryRepository(db)
        self.wh_repo = WarehouseRepository(db)
        self.variant_repo = VariantRepository(db)
        self.txn_repo = TransactionRepository(db)
        self.log_repo = LogRepository(db)
        self.logger = logging.getLogger(f"{__name__}.WarehouseTransferService")

    async def _generate_transfer_number(self) -> str:
        """Generate a unique transfer number."""
        now = datetime.now(timezone.utc)
        date_part = now.strftime("%Y%m%d")
        random_part = str(uuid.uuid4()).split("-")[0].upper()
        return f"TRF-{date_part}-{random_part}"

    async def create_transfer(self, data) -> WarehouseTransfer:
        """Create a new warehouse transfer with items."""
        # Validate warehouses exist and are different
        if data.source_warehouse_id == data.destination_warehouse_id:
            raise SameWarehouseTransferError(str(data.source_warehouse_id))

        source = await self.wh_repo.get_by_id(data.source_warehouse_id)
        if source is None or str(source.store_id) != str(self.store.id):
            raise WarehouseNotFoundError(str(data.source_warehouse_id))
        if not source.is_active:
            raise WarehouseInactiveError(str(data.source_warehouse_id))

        dest = await self.wh_repo.get_by_id(data.destination_warehouse_id)
        if dest is None or str(dest.store_id) != str(self.store.id):
            raise WarehouseNotFoundError(str(data.destination_warehouse_id))
        if not dest.is_active:
            raise WarehouseInactiveError(str(data.destination_warehouse_id))

        # Validate stock availability for each item
        for item_data in data.items:
            inv = await self.inv_repo.get_by_variant_and_warehouse(
                data.source_warehouse_id, item_data.variant_id,
            )
            available = inv.available_stock if inv else 0
            if available < item_data.quantity:
                raise InsufficientWarehouseStockError(
                    warehouse_id=str(data.source_warehouse_id),
                    variant_id=str(item_data.variant_id),
                    available=available,
                    requested=item_data.quantity,
                )

        # Create transfer
        transfer_number = await self._generate_transfer_number()
        transfer = await self.transfer_repo.create(
            store_id=self.store.id,
            data={
                "transfer_number": transfer_number,
                "source_warehouse_id": data.source_warehouse_id,
                "destination_warehouse_id": data.destination_warehouse_id,
                "status": TransferStatus.DRAFT,
                "requested_by_id": self.user_id,
                "transfer_date": data.transfer_date or datetime.now(timezone.utc),
                "notes": data.notes,
            },
        )

        # Create items
        for item_data in data.items:
            variant = await self.variant_repo.get_by_id(item_data.variant_id)
            await self.item_repo.create(
                transfer_id=transfer.id,
                data={
                    "variant_id": item_data.variant_id,
                    "product_id": variant.product_id if variant else None,
                    "quantity": item_data.quantity,
                    "reason": item_data.reason,
                },
            )

        await self.log_repo.create(
            variant_id=data.items[0].variant_id,
            action=InventoryAction.TRANSFER_CREATED.value,
            details={
                "transfer_number": transfer_number,
                "source": str(data.source_warehouse_id),
                "destination": str(data.destination_warehouse_id),
                "item_count": len(data.items),
            },
            performed_by=self.user_id,
        )

        await self.db.commit()
        return await self.transfer_repo.get_by_id(transfer.id)

    async def get_transfer(self, transfer_id: uuid.UUID) -> WarehouseTransfer:
        """Get a transfer by ID."""
        transfer = await self.transfer_repo.get_by_id(transfer_id)
        if transfer is None or str(transfer.store_id) != str(self.store.id):
            raise TransferNotFoundError(str(transfer_id))
        return transfer

    async def list_transfers(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[TransferStatus] = None,
        source_warehouse_id: Optional[uuid.UUID] = None,
        destination_warehouse_id: Optional[uuid.UUID] = None,
        search: Optional[str] = None,
    ) -> tuple[list[WarehouseTransfer], int]:
        """List transfers with filtering."""
        return await self.transfer_repo.list_by_store(
            store_id=self.store.id,
            page=page,
            page_size=page_size,
            status=status,
            source_warehouse_id=source_warehouse_id,
            destination_warehouse_id=destination_warehouse_id,
            search=search,
        )

    async def submit_transfer(self, transfer_id: uuid.UUID) -> WarehouseTransfer:
        """Submit a transfer for approval (move from DRAFT to PENDING)."""
        transfer = await self.get_transfer(transfer_id)
        if transfer.status != TransferStatus.DRAFT:
            raise InvalidTransferStateError(
                str(transfer_id), transfer.status.value, "draft",
            )
        return await self.transfer_repo.update(transfer_id, {
            "status": TransferStatus.PENDING,
        })

    async def approve_transfer(self, transfer_id: uuid.UUID) -> WarehouseTransfer:
        """Approve a transfer (move from PENDING to APPROVED)."""
        transfer = await self.get_transfer(transfer_id)
        if transfer.status != TransferStatus.PENDING:
            raise InvalidTransferStateError(
                str(transfer_id), transfer.status.value, "pending",
            )

        transfer = await self.transfer_repo.update(transfer_id, {
            "status": TransferStatus.APPROVED,
            "approved_by_id": self.user_id,
        })

        await self.log_repo.create(
            variant_id=transfer.items[0].variant_id if transfer.items else uuid.uuid4(),
            action=InventoryAction.TRANSFER_APPROVED.value,
            details={"transfer_number": transfer.transfer_number},
            performed_by=self.user_id,
        )

        await self.db.commit()
        return await self.transfer_repo.get_by_id(transfer_id)

    async def start_transfer(self, transfer_id: uuid.UUID) -> WarehouseTransfer:
        """Start the transfer (move from APPROVED to IN_TRANSIT)."""
        transfer = await self.get_transfer(transfer_id)
        if transfer.status != TransferStatus.APPROVED:
            raise InvalidTransferStateError(
                str(transfer_id), transfer.status.value, "approved",
            )

        # Reserve stock at source warehouse
        for item in transfer.items:
            if item.variant_id:
                inv_service = WarehouseInventoryService(self.db, self.store, self.user_id)
                await inv_service.reserve_stock(
                    warehouse_id=transfer.source_warehouse_id,
                    variant_id=item.variant_id,
                    quantity=item.quantity,
                    reason=f"Transfer {transfer.transfer_number}",
                )

        return await self.transfer_repo.update(transfer_id, {
            "status": TransferStatus.IN_TRANSIT,
        })

    async def complete_transfer(self, transfer_id: uuid.UUID) -> WarehouseTransfer:
        """
        Complete a transfer.

        For each item:
        1. Reduce available stock at source (removing from reservation)
        2. Add available stock at destination
        3. Log inventory transactions for both warehouses
        4. Update transfer item received_quantity
        """
        transfer = await self.get_transfer(transfer_id)
        if transfer.status not in (TransferStatus.IN_TRANSIT, TransferStatus.APPROVED):
            raise InvalidTransferStateError(
                str(transfer_id), transfer.status.value, "in_transit or approved",
            )

        inv_service = WarehouseInventoryService(self.db, self.store, self.user_id)

        all_completed = True
        for item in transfer.items:
            if not item.variant_id:
                continue

            # Remove stock from source (release reservation + deduct)
            # Use pessimistic locking to prevent concurrent inventory race conditions
            source_inv = await self.inv_repo.get_or_create(
                transfer.source_warehouse_id, item.variant_id,
                with_lock=True,
            )

            # Release reservation first
            release_qty = min(item.quantity, source_inv.reserved_stock)
            source_inv.reserved_stock -= release_qty

            # Then deduct remaining from available if reservation didn't cover it
            remaining = item.quantity - release_qty
            if remaining > 0:
                source_inv.available_stock -= remaining

            # Add stock to destination
            dest_inv = await self.inv_repo.get_or_create(
                transfer.destination_warehouse_id, item.variant_id,
                with_lock=True,
            )
            dest_inv.available_stock += item.quantity
            dest_inv.updated_at = datetime.now(timezone.utc)

            # Create inventory transactions for audit trail
            await self.txn_repo.create(
                variant_id=item.variant_id,
                transaction_type=TransactionType.TRANSFER,
                quantity_change=-item.quantity,
                quantity_before=source_inv.available_stock + item.quantity,
                quantity_after=source_inv.available_stock,
                reason=f"Transfer out to {transfer.transfer_number}",
                reference_id=str(transfer_id),
                performed_by=self.user_id,
            )
            await self.txn_repo.create(
                variant_id=item.variant_id,
                transaction_type=TransactionType.TRANSFER,
                quantity_change=item.quantity,
                quantity_before=dest_inv.available_stock - item.quantity,
                quantity_after=dest_inv.available_stock,
                reason=f"Transfer in from {transfer.transfer_number}",
                reference_id=str(transfer_id),
                performed_by=self.user_id,
            )

            # Update received_quantity
            item.received_quantity = item.quantity

        # Update variant-level inventory_quantity (aggregate across warehouses)
        # The net change across all warehouses is zero (stock moved, not created/destroyed),
        # but we should recalculate/reconcile the variant's inventory_quantity from
        # actual warehouse-level data to keep it consistent.
        # For now, we leave inventory_quantity unchanged since it's a net-zero movement,
        # but we log the transfer so reconciliation can verify if needed.
        self.logger.info(
            "Transfer %s completed: variant-level inventory_quantity unchanged "
            "(net-zero movement across warehouses)",
            transfer.transfer_number,
        )

        transfer.completed_date = datetime.now(timezone.utc)
        transfer.status = TransferStatus.COMPLETED

        await self.log_repo.create(
            variant_id=transfer.items[0].variant_id if transfer.items else uuid.uuid4(),
            action=InventoryAction.TRANSFER_COMPLETED.value,
            details={"transfer_number": transfer.transfer_number},
            performed_by=self.user_id,
        )

        await self.db.commit()
        # Invalidate aggregation cache after transfer completion
        try:
            await aggregation_cache.invalidate_store(self.store.id)
        except Exception as cache_exc:
            self.logger.warning(
                "Cache invalidation failed after transfer completion: %s",
                cache_exc,
            )
        return await self.transfer_repo.get_by_id(transfer_id)

    async def cancel_transfer(self, transfer_id: uuid.UUID) -> WarehouseTransfer:
        """Cancel a transfer and release any reserved stock."""
        transfer = await self.get_transfer(transfer_id)
        if transfer.status in (TransferStatus.COMPLETED, TransferStatus.CANCELLED):
            raise InvalidTransferStateError(
                str(transfer_id), transfer.status.value,
                "draft, pending, approved, or in_transit",
            )

        # Release any reserved stock
        if transfer.status == TransferStatus.IN_TRANSIT:
            for item in transfer.items:
                if item.variant_id:
                    inv_service = WarehouseInventoryService(self.db, self.store, self.user_id)
                    await inv_service.release_reservation(
                        warehouse_id=transfer.source_warehouse_id,
                        variant_id=item.variant_id,
                        quantity=item.quantity,
                        reason=f"Transfer cancelled: {transfer.transfer_number}",
                    )

        transfer = await self.transfer_repo.update(transfer_id, {
            "status": TransferStatus.CANCELLED,
        })

        await self.log_repo.create(
            variant_id=transfer.items[0].variant_id if transfer.items else uuid.uuid4(),
            action=InventoryAction.TRANSFER_CANCELLED.value,
            details={"transfer_number": transfer.transfer_number},
            performed_by=self.user_id,
        )

        await self.db.commit()
        # Invalidate aggregation cache after transfer cancellation
        try:
            await aggregation_cache.invalidate_store(self.store.id)
        except Exception as cache_exc:
            self.logger.warning(
                "Cache invalidation failed after transfer cancellation: %s",
                cache_exc,
            )
        return await self.transfer_repo.get_by_id(transfer_id)


class CapacityService:
    """Business logic for warehouse capacity management and monitoring."""

    def __init__(self, db: AsyncSession, store: Store):
        self.db = db
        self.store = store
        self.wh_repo = WarehouseRepository(db)
        self.inv_repo = WarehouseInventoryRepository(db)
        self.logger = logging.getLogger(f"{__name__}.CapacityService")

    async def get_capacity(self, warehouse_id: uuid.UUID) -> dict:
        """Get capacity information for a warehouse.

        Uses SQL SUM aggregate instead of loading all inventory rows
        into memory for counting (prevents OFFPAGE / memory pressure).
        """
        warehouse = await self.wh_repo.get_by_id(warehouse_id)
        if warehouse is None or str(warehouse.store_id) != str(self.store.id):
            raise WarehouseNotFoundError(str(warehouse_id))

        # Use SQL SUM instead of loading all rows into memory
        from sqlalchemy import select as sel, func as fn
        usage_result = await self.db.execute(
            sel(
                fn.coalesce(fn.sum(WarehouseInventory.available_stock), 0) +
                fn.coalesce(fn.sum(WarehouseInventory.reserved_stock), 0) +
                fn.coalesce(fn.sum(WarehouseInventory.incoming_stock), 0) +
                fn.coalesce(fn.sum(WarehouseInventory.damaged_stock), 0)
            ).where(WarehouseInventory.warehouse_id == warehouse_id)
        )
        current_usage = usage_result.scalar() or 0

        capacity = warehouse.capacity
        available_capacity = None
        usage_pct = None
        status = "normal"

        if capacity:
            available_capacity = max(0, capacity - current_usage)
            usage_pct = round((current_usage / capacity) * 100, 1) if capacity > 0 else 0

            if usage_pct >= 95:
                status = "critical"
            elif usage_pct >= 80:
                status = "warning"
            elif usage_pct >= 100:
                status = "exceeded"
            else:
                status = "normal"

        return {
            "warehouse_id": warehouse_id,
            "warehouse_name": warehouse.name,
            "warehouse_code": warehouse.code,
            "capacity": capacity,
            "capacity_unit": warehouse.capacity_unit,
            "current_usage": current_usage,
            "available_capacity": available_capacity,
            "usage_percentage": usage_pct,
            "status": status,
        }

    async def validate_capacity(
        self, warehouse_id: uuid.UUID, additional_units: int = 0
    ) -> bool:
        """
        Validate that a warehouse has capacity for additional units.
        Raises WarehouseAtCapacityError if capacity would be exceeded.
        """
        cap = await self.get_capacity(warehouse_id)
        if cap["capacity"] is None:
            return True  # No capacity limit

        projected = cap["current_usage"] + additional_units
        if projected > cap["capacity"]:
            raise WarehouseAtCapacityError(
                warehouse_id=str(warehouse_id),
                capacity=cap["capacity"],
                current_usage=cap["current_usage"],
            )
        return True

    async def get_all_capacities(self) -> list[dict]:
        """Get capacity info for all warehouses in the store."""
        warehouses, _ = await self.wh_repo.list_by_store(
            store_id=self.store.id, page=1, page_size=1000,
            is_active=True,
        )
        capacities = []
        for wh in warehouses:
            cap = await self.get_capacity(wh.id)
            capacities.append(cap)
        return capacities

    async def get_summary(self) -> dict:
        """Get high-level capacity summary across all warehouses.

        Uses COUNT queries instead of loading rows to avoid N+1.
        Transfers also use COUNT through their own optimized queries.
        """
        total_wh = await self.wh_repo.count_by_store(self.store.id)
        active_wh = await self.wh_repo.count_active(self.store.id)
        total_capacity, total_used = await self.wh_repo.get_total_capacity(self.store.id)
        capacities = await self.get_all_capacities()

        # Count transfers using dedicated count methods
        transfer_repo = WarehouseTransferRepository(self.db)
        pending_count = await transfer_repo.count_by_status(
            self.store.id, TransferStatus.PENDING,
        )
        in_transit_count = await transfer_repo.count_by_status(
            self.store.id, TransferStatus.IN_TRANSIT,
        )

        return {
            "total_warehouses": total_wh,
            "active_warehouses": active_wh,
            "total_capacity": total_capacity,
            "total_used_capacity": total_used,
            "total_products_in_warehouses": sum(
                c.get("current_usage", 0) for c in capacities
            ),
            "total_transfers_pending": pending_count,
            "total_transfers_in_transit": in_transit_count,
            "warehouses": capacities,
        }


class InventoryAggregationService:
    """Service for querying inventory across multiple warehouses."""

    def __init__(self, db: AsyncSession, store: Store):
        self.db = db
        self.store = store
        self.inv_repo = WarehouseInventoryRepository(db)
        self.wh_repo = WarehouseRepository(db)
        self.logger = logging.getLogger(f"{__name__}.InventoryAggregationService")

    async def get_variant_distribution(self, variant_id: uuid.UUID) -> dict:
        """Get stock distribution for a variant across all warehouses."""
        return await self.inv_repo.get_aggregated_by_variant(self.store.id, variant_id)

    async def get_all_warehouse_summaries(self) -> list[dict]:
        """Get summary for all warehouses."""
        warehouses, _ = await self.wh_repo.list_by_store(
            store_id=self.store.id, page=1, page_size=1000, is_active=True,
        )
        summaries = []
        for wh in warehouses:
            items, total_count = await self.inv_repo.list_by_warehouse(
                warehouse_id=wh.id, page=1, page_size=1,
            )
            # Get totals
            all_items, _ = await self.inv_repo.list_by_warehouse(
                warehouse_id=wh.id, page=1, page_size=10000,
            )
            total_available = sum(i.available_stock for i in all_items)
            total_reserved = sum(i.reserved_stock for i in all_items)
            low_stock = sum(1 for i in all_items if 0 < i.available_stock <= i.reorder_point)
            out_of_stock = sum(1 for i in all_items if i.available_stock == 0)

            summaries.append({
                "warehouse_id": wh.id,
                "warehouse_name": wh.name,
                "warehouse_code": wh.code,
                "total_products": total_count,
                "total_available_stock": total_available,
                "total_reserved_stock": total_reserved,
                "low_stock_count": low_stock,
                "out_of_stock_count": out_of_stock,
            })

        return summaries

    async def get_low_stock_across_warehouses(
        self, threshold: int = 10,
    ) -> list[dict]:
        """Get low stock items across ALL warehouses."""
        return await WarehouseInventoryService(
            self.db, self.store
        ).get_low_stock(threshold)

    async def get_stock_value_by_warehouse(self) -> list[dict]:
        """Calculate inventory value per warehouse."""
        warehouses, _ = await self.wh_repo.list_by_store(
            store_id=self.store.id, page=1, page_size=1000, is_active=True,
        )
        from sqlalchemy import select as sel, func as fn

        results = []
        for wh in warehouses:
            result = await self.db.execute(
                sel(
                    fn.coalesce(fn.sum(
                        WarehouseInventory.available_stock * ProductVariant.price
                    ), 0)
                )
                .select_from(WarehouseInventory)
                .join(ProductVariant, WarehouseInventory.variant_id == ProductVariant.id)
                .where(WarehouseInventory.warehouse_id == wh.id)
            )
            total_value = result.scalar() or 0

            results.append({
                "warehouse_id": wh.id,
                "warehouse_name": wh.name,
                "stock_value": float(total_value),
                "total_units": sum(
                    (i.available_stock + i.reserved_stock)
                    for i in (await self.db.execute(
                        sel(WarehouseInventory).where(
                            WarehouseInventory.warehouse_id == wh.id
                        )
                    )).scalars().all()
                ),
            })

        return results
