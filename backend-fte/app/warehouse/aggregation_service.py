"""
Inventory Aggregation & Analytics Service for Warehouse Dashboard.

Provides dashboard-ready data aggregation across all warehouses including:
- Stock distribution across locations
- Low stock monitoring
- Inventory valuation
- Transfer activity
- Capacity usage

All queries use SQL aggregate functions instead of loading rows
into memory for counting (prevents N+1 and memory pressure).
"""

import logging
from typing import Optional
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Warehouse, WarehouseInventory, WarehouseTransfer,
    WarehouseTransferItem, Product, ProductVariant,
    InventoryTransaction, Store,
)
from app.inventory.constants import TransferStatus, TransactionType
from app.warehouse.repository import (
    WarehouseRepository, WarehouseInventoryRepository,
    WarehouseTransferRepository,
)

logger = logging.getLogger(__name__)


class WarehouseDashboardService:
    """Provides aggregated warehouse data for dashboards."""

    def __init__(self, db: AsyncSession, store: Store):
        self.db = db
        self.store = store
        self.wh_repo = WarehouseRepository(db)
        self.inv_repo = WarehouseInventoryRepository(db)
        self.transfer_repo = WarehouseTransferRepository(db)
        self.logger = logging.getLogger(f"{__name__}.WarehouseDashboardService")

    async def get_summary(self) -> dict:
        """Get high-level warehouse summary using COUNT queries instead of loading rows."""
        total_wh = await self.wh_repo.count_by_store(self.store.id)
        active_wh = await self.wh_repo.count_active(self.store.id)
        total_capacity, total_used = await self.wh_repo.get_total_capacity(self.store.id)

        # Count using dedicated COUNT methods instead of loading ORM rows
        pending_count = await self.transfer_repo.count_by_status(
            self.store.id, TransferStatus.PENDING,
        )
        in_transit_count = await self.transfer_repo.count_by_status(
            self.store.id, TransferStatus.IN_TRANSIT,
        )

        # Count low stock items using aggregate
        low_stock_count = await self._count_low_stock_items()

        # Count warehouses with capacity using aggregate
        cap_result = await self.db.execute(
            select(func.count(Warehouse.id)).where(
                Warehouse.store_id == self.store.id,
                Warehouse.is_active == True,
                Warehouse.capacity.isnot(None),
            )
        )
        total_wh_with_cap = cap_result.scalar() or 0

        return {
            "total_warehouses": total_wh,
            "active_warehouses": active_wh,
            "total_capacity": total_capacity,
            "total_used_capacity": total_used,
            "capacity_usage_percentage": round(
                (total_used / total_capacity * 100), 1
            ) if total_capacity > 0 else 0,
            "pending_transfers": pending_count,
            "in_transit_transfers": in_transit_count,
            "low_stock_items": low_stock_count,
            "total_warehouses_with_capacity": total_wh_with_cap,
        }

    async def _count_low_stock_items(self) -> int:
        """Count low stock items across all active warehouses using SQL COUNT."""
        wh_result = await self.db.execute(
            select(Warehouse.id).where(
                Warehouse.store_id == self.store.id,
                Warehouse.is_active == True,
            )
        )
        wh_ids = [row[0] for row in wh_result.all()]
        if not wh_ids:
            return 0

        count_result = await self.db.execute(
            select(func.count(WarehouseInventory.id)).where(
                WarehouseInventory.warehouse_id.in_(wh_ids),
                WarehouseInventory.available_stock <= WarehouseInventory.reorder_point,
                WarehouseInventory.available_stock > 0,
            )
        )
        return count_result.scalar() or 0

    async def get_stock_distribution(self) -> list[dict]:
        """Get stock distribution across all warehouses using SQL aggregates."""
        # Get all active warehouse IDs
        wh_result = await self.db.execute(
            select(
                Warehouse.id,
                Warehouse.name,
                Warehouse.code,
            ).where(
                Warehouse.store_id == self.store.id,
                Warehouse.is_active == True,
            )
        )
        warehouses_raw = wh_result.all()

        distribution = []
        grand_total = 0

        for wh_id, wh_name, wh_code in warehouses_raw:
            # Get aggregates per warehouse in a single query
            agg_result = await self.db.execute(
                select(
                    func.coalesce(func.sum(WarehouseInventory.available_stock), 0),
                    func.coalesce(func.sum(WarehouseInventory.reserved_stock), 0),
                    func.coalesce(func.sum(WarehouseInventory.incoming_stock), 0),
                    func.count(func.distinct(WarehouseInventory.product_id)),
                ).where(WarehouseInventory.warehouse_id == wh_id)
            )
            total_available, total_reserved, total_incoming, product_count = agg_result.one()

            total_stock = (total_available or 0) + (total_reserved or 0)

            distribution.append({
                "warehouse_id": str(wh_id),
                "warehouse_name": wh_name,
                "warehouse_code": wh_code,
                "product_count": product_count or 0,
                "total_available": total_available or 0,
                "total_reserved": total_reserved or 0,
                "total_incoming": total_incoming or 0,
                "total_stock": total_stock,
                "percentage": 0.0,
            })
            grand_total += total_stock

        # Calculate percentages
        if grand_total > 0:
            for d in distribution:
                d["percentage"] = round((d["total_stock"] / grand_total) * 100, 1)

        return distribution

    async def get_recent_transfers(
        self, limit: int = 10,
    ) -> list[dict]:
        """Get recent transfer activity."""
        transfers, _ = await self.transfer_repo.list_by_store(
            store_id=self.store.id, page=1, page_size=limit,
        )
        return [
            {
                "transfer_id": str(t.id),
                "transfer_number": t.transfer_number,
                "status": t.status.value,
                "source_warehouse_name": t.source_warehouse_rel.name if t.source_warehouse_rel else "Unknown",
                "destination_warehouse_name": t.destination_warehouse_rel.name if t.destination_warehouse_rel else "Unknown",
                "total_items": len(t.items) if t.items else 0,
                "total_quantity": sum(i.quantity for i in (t.items or [])),
                "created_at": t.created_at.isoformat(),
                "completed_date": t.completed_date.isoformat() if t.completed_date else None,
            }
            for t in transfers
        ]

    async def get_inventory_value(self) -> dict:
        """Get total inventory value across all warehouses using SQL aggregates."""
        wh_result = await self.db.execute(
            select(Warehouse.id, Warehouse.name).where(
                Warehouse.store_id == self.store.id,
                Warehouse.is_active == True,
            )
        )
        warehouses_raw = wh_result.all()

        total_value = 0.0
        total_units = 0
        wh_values = []

        for wh_id, wh_name in warehouses_raw:
            wh_info = await self._calculate_warehouse_value(wh_id)
            wh_values.append({
                "warehouse_id": str(wh_id),
                "warehouse_name": wh_name,
                "total_value": wh_info["total_value"],
                "total_units": wh_info["total_units"],
                "product_count": wh_info["product_count"],
            })
            total_value += wh_info["total_value"]
            total_units += wh_info["total_units"]

        return {
            "total_value": round(total_value, 2),
            "total_units": total_units,
            "warehouses": wh_values,
        }

    async def _calculate_warehouse_value(self, warehouse_id) -> dict:
        """Calculate inventory value for a single warehouse using SQL aggregate."""
        # Use SQL to calculate total value and count distinct products
        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(
                        WarehouseInventory.available_stock * ProductVariant.price
                    ), 0
                ),
                func.coalesce(func.sum(WarehouseInventory.available_stock), 0),
                func.count(func.distinct(WarehouseInventory.product_id)),
            )
            .select_from(WarehouseInventory)
            .outerjoin(
                ProductVariant,
                WarehouseInventory.variant_id == ProductVariant.id,
            )
            .where(WarehouseInventory.warehouse_id == warehouse_id)
        )
        total_value, total_units, product_count = result.one()

        return {
            "total_value": round(float(total_value or 0), 2),
            "total_units": total_units or 0,
            "product_count": product_count or 0,
        }

    async def get_warehouse_activity(self, days: int = 7) -> list[dict]:
        """Get recent activity across all warehouses using SQL COUNT."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        wh_result = await self.db.execute(
            select(Warehouse.id, Warehouse.name).where(
                Warehouse.store_id == self.store.id,
                Warehouse.is_active == True,
            )
        )
        warehouses_raw = wh_result.all()

        activity = []
        for wh_id, wh_name in warehouses_raw:
            # Count transfers involving this warehouse since date
            src_result = await self.db.execute(
                select(func.count(WarehouseTransfer.id)).where(
                    WarehouseTransfer.source_warehouse_id == wh_id,
                    WarehouseTransfer.created_at >= since,
                )
            )
            dst_result = await self.db.execute(
                select(func.count(WarehouseTransfer.id)).where(
                    WarehouseTransfer.destination_warehouse_id == wh_id,
                    WarehouseTransfer.created_at >= since,
                )
            )
            src_count = src_result.scalar() or 0
            dst_count = dst_result.scalar() or 0

            activity.append({
                "warehouse_id": str(wh_id),
                "warehouse_name": wh_name,
                "transfers_out": src_count,
                "transfers_in": dst_count,
                "total_transfers": src_count + dst_count,
            })

        return sorted(activity, key=lambda x: x["total_transfers"], reverse=True)

    async def get_low_stock_report(self, threshold: int = 10) -> list[dict]:
        """Get comprehensive low stock report across all warehouses."""
        items = await self.inv_repo.get_low_stock_by_store(self.store.id, threshold)
        return [
            {
                "warehouse_id": str(item.warehouse_id),
                "warehouse_name": item.warehouse.name if item.warehouse else "Unknown",
                "variant_id": str(item.variant_id) if item.variant_id else None,
                "product_id": str(item.product_id) if item.product_id else None,
                "product_title": item.product.title if item.product else "Unknown",
                "variant_title": item.variant.title if item.variant else "Unknown",
                "sku": item.variant.sku if item.variant else None,
                "available_stock": item.available_stock,
                "reorder_point": item.reorder_point,
                "minimum_stock": item.minimum_stock,
                "bin_location": item.bin_location,
            }
            for item in items
        ]
