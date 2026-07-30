"""
Repository Layer for the Warehouse Management module.

Each repository encapsulates ALL database operations for its entity.
Follows the same pattern as the Inventory module repositories.
No business logic — only SQLAlchemy queries returning ORM instances.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, and_, or_, update, delete, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.models import (
    Warehouse, WarehouseInventory, WarehouseTransfer,
    WarehouseTransferItem, Product, ProductVariant,
)
from app.inventory.constants import WarehouseStatus, TransferStatus


class WarehouseRepository:
    """Data access for warehouses."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, store_id: uuid.UUID, data: dict) -> Warehouse:
        """Create a new warehouse."""
        warehouse = Warehouse(store_id=store_id, **data)
        self.db.add(warehouse)
        await self.db.flush()
        return warehouse

    async def get_by_id(self, warehouse_id: uuid.UUID) -> Optional[Warehouse]:
        """Get a warehouse by ID."""
        result = await self.db.execute(
            select(Warehouse).where(Warehouse.id == warehouse_id)
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str, store_id: uuid.UUID) -> Optional[Warehouse]:
        """Get a warehouse by code (scoped to store)."""
        result = await self.db.execute(
            select(Warehouse).where(
                Warehouse.code == code,
                Warehouse.store_id == store_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_default(self, store_id: uuid.UUID) -> Optional[Warehouse]:
        """Get the default warehouse for a store."""
        result = await self.db.execute(
            select(Warehouse).where(
                Warehouse.store_id == store_id,
                Warehouse.is_default == True,
                Warehouse.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def clear_default(self, store_id: uuid.UUID, with_lock: bool = True) -> None:
        """
        Clear the default flag for all warehouses in a store.

        Uses SELECT FOR UPDATE when with_lock=True to prevent concurrent
        requests from creating inconsistent default states.

        Always runs the UPDATE after locking, even if no rows are found
        under lock, because a concurrent transaction may have inserted
        a new default between the lock and the check.
        """
        if with_lock:
            # Lock all warehouses for this store before updating
            await self.db.execute(
                select(Warehouse.id)
                .where(
                    Warehouse.store_id == store_id,
                    Warehouse.is_default == True,
                )
                .with_for_update()
            )

        await self.db.execute(
            update(Warehouse)
            .where(
                Warehouse.store_id == store_id,
                Warehouse.is_default == True,
            )
            .values(is_default=False)
        )
        await self.db.flush()

    async def set_default(self, warehouse_id: uuid.UUID, store_id: uuid.UUID) -> Optional[Warehouse]:
        """
        Set a warehouse as the default for its store.

        Uses pessimistic locking (SELECT FOR UPDATE) to prevent concurrent
        requests from creating multiple default warehouses.

        Within a single transaction:
        1. Lock the target warehouse with SELECT FOR UPDATE
        2. Verify ownership, existence, and active status
        3. Lock and clear any existing defaults for this store
        4. Set new default on the target warehouse

        Returns None if warehouse not found, doesn't belong to the store,
        or is not active.
        """
        # Lock the target warehouse with SELECT FOR UPDATE
        lock_result = await self.db.execute(
            select(Warehouse)
            .where(Warehouse.id == warehouse_id)
            .with_for_update()
        )
        warehouse = lock_result.scalar_one_or_none()
        if warehouse is None:
            return None

        if str(warehouse.store_id) != str(store_id):
            return None

        if not warehouse.is_active:
            return None

        # Lock and clear any existing defaults for this store
        await self.clear_default(store_id, with_lock=True)

        # Set the new default
        warehouse.is_default = True
        await self.db.flush()
        return warehouse

    async def ensure_single_default(self, store_id: uuid.UUID) -> Optional[Warehouse]:
        """
        Ensure exactly one default warehouse exists for a store.
        If only one warehouse exists, auto-assign it as default.
        Returns the default warehouse if one exists/created.

        Uses row-level locking when auto-assigning to prevent races.
        """
        existing_default = await self.get_default(store_id)
        if existing_default:
            return existing_default

        # Use COUNT query instead of loading rows
        total = await self.count_active(store_id)
        if total == 1:
            # Only one active warehouse — lock and auto-assign
            result = await self.db.execute(
                select(Warehouse)
                .where(
                    Warehouse.store_id == store_id,
                    Warehouse.is_active == True,
                )
                .with_for_update()
                .limit(1)
            )
            wh = result.scalar_one_or_none()
            if wh:
                wh.is_default = True
                await self.db.flush()
                return wh

        return None

    async def list_by_store(
        self,
        store_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: Optional[WarehouseStatus] = None,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> tuple[list[Warehouse], int]:
        """List warehouses with pagination and filtering."""
        query = select(Warehouse)
        count_query = select(func.count(Warehouse.id))

        conditions = [Warehouse.store_id == store_id]

        if status:
            conditions.append(Warehouse.status == status)
        if is_active is not None:
            conditions.append(Warehouse.is_active == is_active)
        if search:
            pattern = f"%{search}%"
            conditions.append(
                or_(
                    Warehouse.name.ilike(pattern),
                    Warehouse.code.ilike(pattern),
                    Warehouse.city.ilike(pattern),
                )
            )

        where_clause = and_(*conditions)
        query = query.where(where_clause)
        count_query = count_query.where(where_clause)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Warehouse.is_default.desc(), Warehouse.name.asc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        warehouses = list(result.scalars().all())

        return warehouses, total

    async def update(self, warehouse_id: uuid.UUID, data: dict) -> Optional[Warehouse]:
        """Update a warehouse."""
        warehouse = await self.get_by_id(warehouse_id)
        if warehouse is None:
            return None
        for field, value in data.items():
            if hasattr(warehouse, field):
                setattr(warehouse, field, value)
        await self.db.flush()
        return warehouse

    async def delete(self, warehouse_id: uuid.UUID) -> bool:
        """Delete a warehouse."""
        warehouse = await self.get_by_id(warehouse_id)
        if warehouse is None:
            return False
        await self.db.delete(warehouse)
        await self.db.flush()
        return True

    async def count_by_store(self, store_id: uuid.UUID) -> int:
        """Count warehouses for a store using SQL COUNT(*)."""
        result = await self.db.execute(
            select(func.count(Warehouse.id)).where(Warehouse.store_id == store_id)
        )
        return result.scalar() or 0

    async def count_active(self, store_id: uuid.UUID) -> int:
        """Count active warehouses for a store using SQL COUNT(*)."""
        result = await self.db.execute(
            select(func.count(Warehouse.id)).where(
                Warehouse.store_id == store_id,
                Warehouse.is_active == True,
            )
        )
        return result.scalar() or 0

    async def count_default(self, store_id: uuid.UUID) -> int:
        """Count default warehouses for a store using SQL COUNT(*).

        Should always be 0 or 1 — used to detect inconsistencies.
        """
        result = await self.db.execute(
            select(func.count(Warehouse.id)).where(
                Warehouse.store_id == store_id,
                Warehouse.is_default == True,
            )
        )
        return result.scalar() or 0

    async def get_total_capacity(self, store_id: uuid.UUID) -> tuple[int, int]:
        """
        Get total and used capacity across all active warehouses for a store.

        Uses SQL aggregate functions instead of loading rows into memory.
        """
        # Get total capacity via SQL SUM (only warehouses with capacity set)
        capacity_result = await self.db.execute(
            select(
                func.coalesce(func.sum(Warehouse.capacity), 0)
            ).where(
                Warehouse.store_id == store_id,
                Warehouse.is_active == True,
                Warehouse.capacity.isnot(None),
            )
        )
        total_capacity = capacity_result.scalar() or 0

        # Get IDs of active warehouses for inventory sum
        wh_id_result = await self.db.execute(
            select(Warehouse.id).where(
                Warehouse.store_id == store_id,
                Warehouse.is_active == True,
            )
        )
        wh_ids = [row[0] for row in wh_id_result.all()]

        if wh_ids:
            usage_result = await self.db.execute(
                select(
                    func.coalesce(func.sum(WarehouseInventory.available_stock), 0) +
                    func.coalesce(func.sum(WarehouseInventory.reserved_stock), 0) +
                    func.coalesce(func.sum(WarehouseInventory.incoming_stock), 0) +
                    func.coalesce(func.sum(WarehouseInventory.damaged_stock), 0)
                ).where(WarehouseInventory.warehouse_id.in_(wh_ids))
            )
            total_used = usage_result.scalar() or 0
        else:
            total_used = 0

        return total_capacity, total_used


class WarehouseInventoryRepository:
    """Data access for warehouse inventory records."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create(
        self,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        with_lock: bool = False,
    ) -> WarehouseInventory:
        """Get existing inventory record or create a new one."""
        query = select(WarehouseInventory).where(
            WarehouseInventory.warehouse_id == warehouse_id,
            WarehouseInventory.variant_id == variant_id,
        )
        if with_lock:
            query = query.with_for_update()
        result = await self.db.execute(query)
        inv = result.scalar_one_or_none()
        if inv:
            return inv

        # Get product_id from variant
        variant_result = await self.db.execute(
            select(ProductVariant).where(ProductVariant.id == variant_id)
        )
        variant = variant_result.scalar_one_or_none()
        product_id = variant.product_id if variant else None

        inv = WarehouseInventory(
            warehouse_id=warehouse_id,
            variant_id=variant_id,
            product_id=product_id,
        )
        self.db.add(inv)
        await self.db.flush()
        return inv

    async def get_by_id(self, inventory_id: uuid.UUID) -> Optional[WarehouseInventory]:
        """Get inventory record by ID."""
        result = await self.db.execute(
            select(WarehouseInventory).where(WarehouseInventory.id == inventory_id)
        )
        return result.scalar_one_or_none()

    async def get_by_variant_and_warehouse(
        self,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        with_lock: bool = False,
    ) -> Optional[WarehouseInventory]:
        """Get inventory for a specific variant at a specific warehouse."""
        query = select(WarehouseInventory).where(
            WarehouseInventory.warehouse_id == warehouse_id,
            WarehouseInventory.variant_id == variant_id,
        )
        if with_lock:
            query = query.with_for_update()
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_by_warehouse(
        self,
        warehouse_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
        low_stock_only: bool = False,
        search: Optional[str] = None,
    ) -> tuple[list[WarehouseInventory], int]:
        """List inventory records for a warehouse."""

        # Build query with joins to product/variant for enriched data
        query = select(WarehouseInventory)
        count_query = select(func.count(WarehouseInventory.id))

        conditions = [WarehouseInventory.warehouse_id == warehouse_id]

        if low_stock_only:
            conditions.append(
                WarehouseInventory.available_stock <= WarehouseInventory.reorder_point
            )
            conditions.append(WarehouseInventory.available_stock > 0)

        if search:
            pattern = f"%{search}%"
            # We need to join to search by product/variant titles
            query = query.outerjoin(
                ProductVariant, WarehouseInventory.variant_id == ProductVariant.id
            ).outerjoin(
                Product, WarehouseInventory.product_id == Product.id
            )
            conditions.append(
                or_(
                    ProductVariant.sku.ilike(pattern),
                    ProductVariant.title.ilike(pattern),
                    Product.title.ilike(pattern),
                )
            )
        else:
            # Eagerly load variant and product to prevent N+1 queries
            query = query.options(
                selectinload(WarehouseInventory.variant),
                selectinload(WarehouseInventory.product),
            )

        where_clause = and_(*conditions)
        query = query.where(where_clause)
        count_query = count_query.where(where_clause)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(WarehouseInventory.updated_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        # Use unique() because of joined loads
        items = list(result.unique().scalars().all())

        return items, total

    async def update(
        self, inventory_id: uuid.UUID, data: dict
    ) -> Optional[WarehouseInventory]:
        """Update inventory record."""
        inv = await self.get_by_id(inventory_id)
        if inv is None:
            return None
        for field, value in data.items():
            if hasattr(inv, field):
                setattr(inv, field, value)
        inv.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return inv

    async def get_low_stock_by_store(
        self, store_id: uuid.UUID, threshold: int = 10
    ) -> list[WarehouseInventory]:
        """Get all low-stock inventory records across all warehouses for a store."""
        # Find warehouse IDs for the store
        wh_result = await self.db.execute(
            select(Warehouse.id).where(
                Warehouse.store_id == store_id,
                Warehouse.is_active == True,
            )
        )
        wh_ids = [r[0] for r in wh_result.all()]

        if not wh_ids:
            return []

        result = await self.db.execute(
            select(WarehouseInventory)
            .options(joinedload(WarehouseInventory.warehouse))
            .where(
                WarehouseInventory.warehouse_id.in_(wh_ids),
                WarehouseInventory.available_stock <= threshold,
                WarehouseInventory.available_stock > 0,
            )
            .order_by(WarehouseInventory.available_stock.asc())
        )
        return list(result.unique().scalars().all())

    async def get_aggregated_by_variant(
        self, store_id: uuid.UUID, variant_id: uuid.UUID
    ) -> dict:
        """Get aggregated inventory for a variant across all warehouses."""
        wh_result = await self.db.execute(
            select(Warehouse.id).where(
                Warehouse.store_id == store_id,
                Warehouse.is_active == True,
            )
        )
        wh_ids = [r[0] for r in wh_result.all()]

        if not wh_ids:
            return {
                "total_available": 0, "total_reserved": 0,
                "total_incoming": 0, "total_damaged": 0,
                "warehouses": [],
            }

        result = await self.db.execute(
            select(WarehouseInventory).where(
                WarehouseInventory.warehouse_id.in_(wh_ids),
                WarehouseInventory.variant_id == variant_id,
            )
            .options(joinedload(WarehouseInventory.warehouse))
        )
        records = list(result.unique().scalars().all())

        return {
            "total_available": sum(r.available_stock for r in records),
            "total_reserved": sum(r.reserved_stock for r in records),
            "total_incoming": sum(r.incoming_stock for r in records),
            "total_damaged": sum(r.damaged_stock for r in records),
            "warehouses": [
                {
                    "warehouse_id": r.warehouse_id,
                    "warehouse_name": r.warehouse.name if r.warehouse else "Unknown",
                    "available": r.available_stock,
                    "reserved": r.reserved_stock,
                    "incoming": r.incoming_stock,
                }
                for r in records
            ],
        }

    # ══════════════════════════════════════════════════════════════
    # F.12 — AGGREGATE METHODS (Phase 6)
    # ══════════════════════════════════════════════════════════════

    async def aggregate_store(self, wh_ids: list[uuid.UUID]) -> dict:
        """
        Aggregate store-level inventory totals using SQL aggregate functions.

        Returns:
            total_available, total_reserved, total_incoming, total_damaged,
            product_count, variant_count
        """
        if not wh_ids:
            return {
                "total_available": 0, "total_reserved": 0,
                "total_incoming": 0, "total_damaged": 0,
                "product_count": 0, "variant_count": 0,
            }

        result = await self.db.execute(
            select(
                func.coalesce(func.sum(WarehouseInventory.available_stock), 0).label("total_available"),
                func.coalesce(func.sum(WarehouseInventory.reserved_stock), 0).label("total_reserved"),
                func.coalesce(func.sum(WarehouseInventory.incoming_stock), 0).label("total_incoming"),
                func.coalesce(func.sum(WarehouseInventory.damaged_stock), 0).label("total_damaged"),
                func.count(func.distinct(WarehouseInventory.product_id)).label("product_count"),
                func.count(func.distinct(WarehouseInventory.variant_id)).label("variant_count"),
            ).where(WarehouseInventory.warehouse_id.in_(wh_ids))
        )
        row = result.one()
        return {
            "total_available": row.total_available or 0,
            "total_reserved": row.total_reserved or 0,
            "total_incoming": row.total_incoming or 0,
            "total_damaged": row.total_damaged or 0,
            "product_count": row.product_count or 0,
            "variant_count": row.variant_count or 0,
        }

    async def aggregate_dashboard(self, wh_ids: list[uuid.UUID]) -> dict:
        """
        Aggregate dashboard-level inventory totals using SQL aggregate functions.

        Returns aggregated totals plus inventory_value estimate.
        """
        if not wh_ids:
            return {
                "total_available": 0, "total_reserved": 0,
                "total_incoming": 0, "total_damaged": 0,
                "inventory_value": 0.0,
            }

        result = await self.db.execute(
            select(
                func.coalesce(func.sum(WarehouseInventory.available_stock), 0).label("total_available"),
                func.coalesce(func.sum(WarehouseInventory.reserved_stock), 0).label("total_reserved"),
                func.coalesce(func.sum(WarehouseInventory.incoming_stock), 0).label("total_incoming"),
                func.coalesce(func.sum(WarehouseInventory.damaged_stock), 0).label("total_damaged"),
            ).where(WarehouseInventory.warehouse_id.in_(wh_ids))
        )
        row = result.one()

        # Inventory value
        value_result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(WarehouseInventory.available_stock * ProductVariant.price), 0
                )
            )
            .select_from(WarehouseInventory)
            .join(ProductVariant, WarehouseInventory.variant_id == ProductVariant.id)
            .where(WarehouseInventory.warehouse_id.in_(wh_ids))
        )
        inventory_value = float(value_result.scalar() or 0)

        return {
            "total_available": row.total_available or 0,
            "total_reserved": row.total_reserved or 0,
            "total_incoming": row.total_incoming or 0,
            "total_damaged": row.total_damaged or 0,
            "inventory_value": inventory_value,
        }

    async def aggregate_warehouse(self, warehouse_id: uuid.UUID) -> dict:
        """
        Aggregate inventory for a single warehouse using SQL aggregate functions.

        Returns:
            total_available, total_reserved, total_incoming, total_damaged,
            total_records, variant_count, product_count
        """
        result = await self.db.execute(
            select(
                func.coalesce(func.sum(WarehouseInventory.available_stock), 0).label("total_available"),
                func.coalesce(func.sum(WarehouseInventory.reserved_stock), 0).label("total_reserved"),
                func.coalesce(func.sum(WarehouseInventory.incoming_stock), 0).label("total_incoming"),
                func.coalesce(func.sum(WarehouseInventory.damaged_stock), 0).label("total_damaged"),
                func.count(WarehouseInventory.id).label("total_records"),
                func.count(func.distinct(WarehouseInventory.variant_id)).label("variant_count"),
                func.count(func.distinct(WarehouseInventory.product_id)).label("product_count"),
            ).where(WarehouseInventory.warehouse_id == warehouse_id)
        )
        row = result.one()
        return {
            "total_available": row.total_available or 0,
            "total_reserved": row.total_reserved or 0,
            "total_incoming": row.total_incoming or 0,
            "total_damaged": row.total_damaged or 0,
            "total_records": row.total_records or 0,
            "variant_count": row.variant_count or 0,
            "product_count": row.product_count or 0,
        }

    async def aggregate_inventory_value(self, wh_ids: list[uuid.UUID]) -> float:
        """
        Calculate total inventory value across warehouses using SQL aggregate.

        Uses SUM(available_stock * ProductVariant.price) with GROUP BY.
        """
        if not wh_ids:
            return 0.0

        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(
                        WarehouseInventory.available_stock * ProductVariant.price
                    ), 0
                )
            )
            .select_from(WarehouseInventory)
            .join(ProductVariant, WarehouseInventory.variant_id == ProductVariant.id)
            .where(WarehouseInventory.warehouse_id.in_(wh_ids))
        )
        return float(result.scalar() or 0)

    async def aggregate_capacity(self, wh_ids: list[uuid.UUID]) -> dict[str, dict]:
        """
        Aggregate capacity data for warehouses using a single GROUP BY query.

        Returns dict of {warehouse_id_str: {total_stock, record_count}}

        Used by the engine to batch warehouse utilization calculations,
        eliminating N+1 capacity queries.
        """
        if not wh_ids:
            return {}

        result = await self.db.execute(
            select(
                WarehouseInventory.warehouse_id,
                func.coalesce(
                    func.sum(WarehouseInventory.available_stock) +
                    func.sum(WarehouseInventory.reserved_stock) +
                    func.sum(WarehouseInventory.incoming_stock) +
                    func.sum(WarehouseInventory.damaged_stock), 0
                ).label("total_stock"),
                func.count(WarehouseInventory.id).label("record_count"),
            )
            .where(WarehouseInventory.warehouse_id.in_(wh_ids))
            .group_by(WarehouseInventory.warehouse_id)
        )
        return {
            str(r.warehouse_id): {
                "total_stock": r.total_stock or 0,
                "record_count": r.record_count or 0,
            }
            for r in result.all()
        }

    async def distribution(self, variant_id: uuid.UUID, wh_ids: list[uuid.UUID]) -> list[dict]:
        """
        Get stock distribution for a variant across warehouses using SQL GROUP BY.

        Returns per-warehouse available/reserved/incoming/damaged breakdo
wn."""
        if not wh_ids:
            return []

        result = await self.db.execute(
            select(
                WarehouseInventory.warehouse_id,
                func.coalesce(func.sum(WarehouseInventory.available_stock), 0).label("available"),
                func.coalesce(func.sum(WarehouseInventory.reserved_stock), 0).label("reserved"),
                func.coalesce(func.sum(WarehouseInventory.incoming_stock), 0).label("incoming"),
                func.coalesce(func.sum(WarehouseInventory.damaged_stock), 0).label("damaged"),
            ).where(
                WarehouseInventory.warehouse_id.in_(wh_ids),
                WarehouseInventory.variant_id == variant_id,
            ).group_by(WarehouseInventory.warehouse_id)
        )
        return [
            {
                "warehouse_id": str(r.warehouse_id),
                "available": r.available or 0,
                "reserved": r.reserved or 0,
                "incoming": r.incoming or 0,
                "damaged": r.damaged or 0,
            }
            for r in result.all()
        ]


class WarehouseTransferRepository:
    """Data access for warehouse transfers."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, store_id: uuid.UUID, data: dict) -> WarehouseTransfer:
        """Create a new transfer."""
        transfer = WarehouseTransfer(store_id=store_id, **data)
        self.db.add(transfer)
        await self.db.flush()
        return transfer

    async def get_by_id(
        self, transfer_id: uuid.UUID
    ) -> Optional[WarehouseTransfer]:
        """Get a transfer by ID with items loaded."""
        result = await self.db.execute(
            select(WarehouseTransfer)
            .options(
                selectinload(WarehouseTransfer.items),
                joinedload(WarehouseTransfer.source_warehouse_rel),
                joinedload(WarehouseTransfer.destination_warehouse_rel),
                joinedload(WarehouseTransfer.requested_by),
                joinedload(WarehouseTransfer.approved_by),
            )
            .where(WarehouseTransfer.id == transfer_id)
        )
        return result.unique().scalar_one_or_none()

    async def get_by_transfer_number(
        self, transfer_number: str
    ) -> Optional[WarehouseTransfer]:
        """Get a transfer by its number."""
        result = await self.db.execute(
            select(WarehouseTransfer).where(
                WarehouseTransfer.transfer_number == transfer_number
            )
        )
        return result.scalar_one_or_none()

    async def list_by_store(
        self,
        store_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: Optional[TransferStatus] = None,
        source_warehouse_id: Optional[uuid.UUID] = None,
        destination_warehouse_id: Optional[uuid.UUID] = None,
        search: Optional[str] = None,
    ) -> tuple[list[WarehouseTransfer], int]:
        """List transfers with pagination and filtering."""
        query = select(WarehouseTransfer).options(
            selectinload(WarehouseTransfer.items),
            joinedload(WarehouseTransfer.source_warehouse_rel),
            joinedload(WarehouseTransfer.destination_warehouse_rel),
        )
        count_query = select(func.count(WarehouseTransfer.id))

        conditions = [WarehouseTransfer.store_id == store_id]

        if status:
            conditions.append(WarehouseTransfer.status == status)
        if source_warehouse_id:
            conditions.append(
                WarehouseTransfer.source_warehouse_id == source_warehouse_id
            )
        if destination_warehouse_id:
            conditions.append(
                WarehouseTransfer.destination_warehouse_id == destination_warehouse_id
            )
        if search:
            pattern = f"%{search}%"
            conditions.append(WarehouseTransfer.transfer_number.ilike(pattern))

        where_clause = and_(*conditions)
        query = query.where(where_clause)
        count_query = count_query.where(where_clause)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(WarehouseTransfer.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        transfers = list(result.unique().scalars().all())

        return transfers, total

    async def update(
        self, transfer_id: uuid.UUID, data: dict
    ) -> Optional[WarehouseTransfer]:
        """Update a transfer record."""
        transfer = await self.get_by_id(transfer_id)
        if transfer is None:
            return None
        for field, value in data.items():
            if hasattr(transfer, field):
                setattr(transfer, field, value)
        await self.db.flush()
        return transfer

    async def count_by_status(
        self, store_id: uuid.UUID, status: TransferStatus,
    ) -> int:
        """
        Count transfers for a store by status using SQL COUNT(*).

        Avoids loading ORM rows just for counting.
        """
        result = await self.db.execute(
            select(func.count(WarehouseTransfer.id)).where(
                WarehouseTransfer.store_id == store_id,
                WarehouseTransfer.status == status,
            )
        )
        return result.scalar() or 0

    async def count_by_status_and_warehouse(
        self,
        store_id: uuid.UUID,
        status: TransferStatus,
        warehouse_id: uuid.UUID,
        as_source: bool = True,
    ) -> int:
        """
        Count transfers for a specific warehouse by status using SQL COUNT(*).

        Args:
            store_id: The store to scope the query.
            status: The transfer status to filter by.
            warehouse_id: The warehouse ID.
            as_source: If True, counts transfers where this warehouse is source.
                       If False, counts where this warehouse is destination.
        """
        if as_source:
            condition = WarehouseTransfer.source_warehouse_id == warehouse_id
        else:
            condition = WarehouseTransfer.destination_warehouse_id == warehouse_id

        result = await self.db.execute(
            select(func.count(WarehouseTransfer.id)).where(
                WarehouseTransfer.store_id == store_id,
                WarehouseTransfer.status == status,
                condition,
            )
        )
        return result.scalar() or 0


class WarehouseSettingsRepository:
    """Data access for warehouse settings."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_store(self, store_id: uuid.UUID) -> Optional["WarehouseSettings"]:
        """Get settings for a store, returns None if not yet created."""
        from app.models import WarehouseSettings
        result = await self.db.execute(
            select(WarehouseSettings).where(WarehouseSettings.store_id == store_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, store_id: uuid.UUID) -> "WarehouseSettings":
        """Get existing settings or create default settings for a store."""
        from app.models import WarehouseSettings
        existing = await self.get_by_store(store_id)
        if existing:
            return existing
        settings = WarehouseSettings(store_id=store_id)
        self.db.add(settings)
        await self.db.flush()
        return settings

    async def update(
        self, store_id: uuid.UUID, data: dict
    ) -> Optional["WarehouseSettings"]:
        """Update settings for a store."""
        from app.models import WarehouseSettings
        settings = await self.get_by_store(store_id)
        if settings is None:
            return None
        for field, value in data.items():
            if hasattr(settings, field) and value is not None:
                setattr(settings, field, value)
        await self.db.flush()
        return settings


class WarehouseTransferItemRepository:
    """Data access for transfer items."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, transfer_id: uuid.UUID, data: dict) -> WarehouseTransferItem:
        """Create a transfer item."""
        item = WarehouseTransferItem(transfer_id=transfer_id, **data)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_by_transfer(
        self, transfer_id: uuid.UUID
    ) -> list[WarehouseTransferItem]:
        """Get all items for a transfer."""
        result = await self.db.execute(
            select(WarehouseTransferItem)
            .options(
                joinedload(WarehouseTransferItem.product),
                joinedload(WarehouseTransferItem.variant),
            )
            .where(WarehouseTransferItem.transfer_id == transfer_id)
        )
        return list(result.unique().scalars().all())
