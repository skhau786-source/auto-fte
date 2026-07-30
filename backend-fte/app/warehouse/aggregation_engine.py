"""
Inventory Aggregation Engine — Phase 6 (F.1–F.5, F.8, F.9, F.11).

Centralized service providing real-time inventory visibility across all warehouses.

All queries use SQL aggregate functions (SUM, COUNT, GROUP BY) instead of
loading rows into memory. Designed to answer:

  Total Stock | Available Stock | Reserved Stock | Incoming Stock |
  Damaged Stock | Allocated Stock | Transfer In Transit | Warehouse Distribution

without duplicating calculations or loading unnecessary rows.

Reuses existing services:
- WarehouseInventoryRepository (optimized aggregate methods)
- WarehouseRepository (warehouse listing)
- WarehouseTransferRepository (transfer counts)
- CapacityService (capacity calculations)
- InventoryAggregationCache (caching layer — F.10)
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import (
    Store, Warehouse, WarehouseInventory, WarehouseTransfer,
    WarehouseTransferItem, Product, ProductVariant, InventoryReservation,
)
from app.inventory.constants import TransferStatus, ReservationStatus
from app.warehouse.repository import (
    WarehouseRepository, WarehouseInventoryRepository,
    WarehouseTransferRepository,
)
from app.warehouse.service import CapacityService
from app.warehouse.exceptions import WarehouseNotFoundError
from app.warehouse.aggregation_cache import InventoryAggregationCache

logger = logging.getLogger(__name__)


class InventoryAggregationEngine:
    """
    Centralized inventory aggregation service.

    Every method:
    - Uses SQL aggregate functions (no row-loading for counts)
    - Validates ownership (cross-store access prevented)
    - Returns consistent, structured dicts
    - Supports optional caching via InventoryAggregationCache (F.10)

    Usage:
        engine = InventoryAggregationEngine(db=db, store=store)
        variant = await engine.get_variant(variant_id)
        product = await engine.get_product(product_id)
        warehouse = await engine.get_warehouse(wh_id)
        store_total = await engine.get_store()
    """

    def __init__(
        self,
        db: AsyncSession,
        store: Store,
        user_id: Optional[uuid.UUID] = None,
        cache: Optional[InventoryAggregationCache] = None,
    ):
        self.db = db
        self.store = store
        self.user_id = user_id
        self.wh_repo = WarehouseRepository(db)
        self.inv_repo = WarehouseInventoryRepository(db)
        self.transfer_repo = WarehouseTransferRepository(db)
        self.capacity_service = CapacityService(db, store)
        self.cache = cache or InventoryAggregationCache()
        self.logger = logging.getLogger(f"{__name__}.InventoryAggregationEngine")

    # ═══════════════════════════════════════════════════════════════
    # F.2 — VARIANT AGGREGATION
    # ═══════════════════════════════════════════════════════════════

    async def get_variant(self, variant_id: uuid.UUID) -> dict:
        """
        Aggregate inventory for a single variant across all warehouses.
        """
        # Check cache first
        cache_key = InventoryAggregationCache.key_variant(self.store.id, variant_id)
        cached = await self.cache.get(cache_key)
        if cached is not None:
            return cached

        # Validate variant exists
        variant = await self.db.execute(
            select(ProductVariant).where(
                ProductVariant.id == variant_id,
            )
        )
        variant = variant.scalar_one_or_none()
        if variant is None:
            empty = self._empty_variant(variant_id)
            await self.cache.set(cache_key, empty, ttl=30)
            return empty

        # Get active warehouse IDs for the store
        wh_ids = await self._get_active_warehouse_ids()

        if not wh_ids:
            empty = self._empty_variant(variant_id)
            await self.cache.set(cache_key, empty, ttl=30)
            return empty

        # Batch aggregate: single query gets totals across all warehouses
        agg_result = await self.db.execute(
            select(
                func.coalesce(func.sum(WarehouseInventory.available_stock), 0).label("total_available"),
                func.coalesce(func.sum(WarehouseInventory.reserved_stock), 0).label("total_reserved"),
                func.coalesce(func.sum(WarehouseInventory.incoming_stock), 0).label("total_incoming"),
                func.coalesce(func.sum(WarehouseInventory.damaged_stock), 0).label("total_damaged"),
                func.count(WarehouseInventory.id).label("warehouse_count"),
            ).where(
                WarehouseInventory.warehouse_id.in_(wh_ids),
                WarehouseInventory.variant_id == variant_id,
            )
        )
        row = agg_result.one()
        total_available = row.total_available or 0
        total_reserved = row.total_reserved or 0
        total_incoming = row.total_incoming or 0
        total_damaged = row.total_damaged or 0

        # Count active reservations for this variant
        reserved_count_result = await self.db.execute(
            select(func.count(InventoryReservation.id)).where(
                InventoryReservation.variant_id == variant_id,
                InventoryReservation.store_id == self.store.id,
                InventoryReservation.status.in_([
                    ReservationStatus.ACTIVE, ReservationStatus.PENDING,
                ]),
            )
        )
        reservation_count = reserved_count_result.scalar() or 0

        # In-transit stock: count transfers involving this variant
        in_transit_result = await self.db.execute(
            select(func.coalesce(func.sum(WarehouseTransferItem.quantity), 0))
            .select_from(WarehouseTransfer)
            .join(WarehouseTransferItem)
            .where(
                WarehouseTransfer.store_id == self.store.id,
                WarehouseTransfer.status == TransferStatus.IN_TRANSIT,
                WarehouseTransferItem.variant_id == variant_id,
            )
        )
        in_transit_stock = in_transit_result.scalar() or 0

        # Warehouse breakdown — aggregate per warehouse in a single GROUP BY query
        breakdown_result = await self.db.execute(
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

        # Enrich warehouse breakdown with names
        wh_map = await self._get_warehouse_name_map(wh_ids)
        breakdown = []
        for br in breakdown_result.all():
            wh_id_str = str(br.warehouse_id)
            breakdown.append({
                "warehouse_id": wh_id_str,
                "warehouse_name": wh_map.get(wh_id_str, "Unknown"),
                "available": br.available or 0,
                "reserved": br.reserved or 0,
                "incoming": br.incoming or 0,
                "damaged": br.damaged or 0,
                "total": (br.available or 0) + (br.reserved or 0),
            })

        total_stock = total_available + total_reserved + total_incoming

        result = {
            "variant_id": str(variant_id),
            "product_id": str(variant.product_id) if variant.product_id else None,
            "sku": variant.sku,
            "title": variant.title,
            "total_stock": total_stock,
            "available_stock": total_available,
            "reserved_stock": total_reserved,
            "incoming_stock": total_incoming,
            "damaged_stock": total_damaged,
            "allocated_stock": reservation_count,
            "in_transit_stock": in_transit_stock,
            "warehouse_count": len(breakdown),
            "warehouse_breakdown": breakdown,
        }

        # Cache the result (shorter TTL for variant-level data)
        await self.cache.set(cache_key, result, ttl=30)
        return result

    # ═══════════════════════════════════════════════════════════════
    # F.3 — PRODUCT AGGREGATION
    # ═══════════════════════════════════════════════════════════════

    async def get_product(self, product_id: uuid.UUID) -> dict:
        """
        Aggregate inventory for an entire product (all variants, all warehouses).
        """
        # Check cache first
        cache_key = InventoryAggregationCache.key_product(self.store.id, product_id)
        cached = await self.cache.get(cache_key)
        if cached is not None:
            return cached

        # Validate product
        product = await self.db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = product.scalar_one_or_none()
        if product is None:
            empty = self._empty_product(product_id)
            await self.cache.set(cache_key, empty, ttl=30)
            return empty

        wh_ids = await self._get_active_warehouse_ids()
        if not wh_ids:
            empty = self._empty_product(product_id)
            await self.cache.set(cache_key, empty, ttl=30)
            return empty

        # Get variant IDs for this product
        variant_result = await self.db.execute(
            select(ProductVariant.id).where(
                ProductVariant.product_id == product_id,
            )
        )
        variant_ids = [r[0] for r in variant_result.all()]
        if not variant_ids:
            empty = self._empty_product(product_id, variant_count=0)
            await self.cache.set(cache_key, empty, ttl=30)
            return empty

        # Batch aggregate across all variants and warehouses
        agg_result = await self.db.execute(
            select(
                func.coalesce(func.sum(WarehouseInventory.available_stock), 0).label("total_available"),
                func.coalesce(func.sum(WarehouseInventory.reserved_stock), 0).label("total_reserved"),
                func.coalesce(func.sum(WarehouseInventory.incoming_stock), 0).label("total_incoming"),
                func.coalesce(func.sum(WarehouseInventory.damaged_stock), 0).label("total_damaged"),
            ).where(
                WarehouseInventory.warehouse_id.in_(wh_ids),
                WarehouseInventory.variant_id.in_(variant_ids),
            )
        )
        row = agg_result.one()

        # Count distinct warehouses with stock
        wh_count_result = await self.db.execute(
            select(func.count(func.distinct(WarehouseInventory.warehouse_id)))
            .where(
                WarehouseInventory.warehouse_id.in_(wh_ids),
                WarehouseInventory.variant_id.in_(variant_ids),
                WarehouseInventory.available_stock > 0,
            )
        )
        wh_with_stock = wh_count_result.scalar() or 0

        # Variant breakdown — batch ALL variants in a single GROUP BY query
        agg_result = await self.db.execute(
            select(
                WarehouseInventory.variant_id,
                func.coalesce(func.sum(WarehouseInventory.available_stock), 0).label("available"),
                func.coalesce(func.sum(WarehouseInventory.reserved_stock), 0).label("reserved"),
                func.coalesce(func.sum(WarehouseInventory.incoming_stock), 0).label("incoming"),
                func.coalesce(func.sum(WarehouseInventory.damaged_stock), 0).label("damaged"),
                func.count(WarehouseInventory.warehouse_id).label("wh_count"),
            ).where(
                WarehouseInventory.warehouse_id.in_(wh_ids),
                WarehouseInventory.variant_id.in_(variant_ids),
            ).group_by(WarehouseInventory.variant_id)
        )
        agg_rows = {str(r.variant_id): r for r in agg_result.all()}

        # Batch get variant titles/skus in a single query
        v_info_result = await self.db.execute(
            select(ProductVariant.id, ProductVariant.sku, ProductVariant.title).where(
                ProductVariant.id.in_(variant_ids),
            )
        )
        v_info_map = {str(r[0]): {"sku": r[1], "title": r[2]} for r in v_info_result.all()}

        variant_breakdown = []
        for v_id in variant_ids:
            v_id_str = str(v_id)
            row_v = agg_rows.get(v_id_str)
            info = v_info_map.get(v_id_str, {})
            available = row_v.available if row_v else 0
            reserved = row_v.reserved if row_v else 0
            variant_breakdown.append({
                "variant_id": v_id_str,
                "sku": info.get("sku"),
                "title": info.get("title"),
                "available": available or 0,
                "reserved": reserved or 0,
                "incoming": row_v.incoming if row_v else 0,
                "damaged": row_v.damaged if row_v else 0,
                "total": (available or 0) + (reserved or 0),
                "warehouse_count": row_v.wh_count if row_v else 0,
            })

        result = {
            "product_id": str(product_id),
            "title": product.title,
            "total_available": row.total_available or 0,
            "total_reserved": row.total_reserved or 0,
            "total_incoming": row.total_incoming or 0,
            "total_damaged": row.total_damaged or 0,
            "variant_count": len(variant_ids),
            "warehouse_count": wh_with_stock,
            "variant_breakdown": variant_breakdown,
        }

        await self.cache.set(cache_key, result, ttl=30)
        return result

    # ═══════════════════════════════════════════════════════════════
    # F.4 — WAREHOUSE AGGREGATION
    # ═══════════════════════════════════════════════════════════════

    async def get_warehouse(self, warehouse_id: uuid.UUID) -> dict:
        """
        Aggregate inventory for a single warehouse.
        """
        # Check cache first
        cache_key = InventoryAggregationCache.key_warehouse(self.store.id, warehouse_id)
        cached = await self.cache.get(cache_key)
        if cached is not None:
            return cached

        warehouse = await self.wh_repo.get_by_id(warehouse_id)
        if warehouse is None or str(warehouse.store_id) != str(self.store.id):
            raise WarehouseNotFoundError(str(warehouse_id))

        # Use repository aggregate method for warehouse-level totals
        warehouse_agg = await self.inv_repo.aggregate_warehouse(warehouse_id)

        # SKU count (need to join to ProductVariant for SKU)
        sku_result = await self.db.execute(
            select(func.count(func.distinct(ProductVariant.sku)))
            .select_from(WarehouseInventory)
            .join(ProductVariant, WarehouseInventory.variant_id == ProductVariant.id)
            .where(
                WarehouseInventory.warehouse_id == warehouse_id,
                ProductVariant.sku.isnot(None),
                ProductVariant.sku != "",
            )
        )
        sku_count = sku_result.scalar() or 0

        # Active reservations at this warehouse
        reservation_result = await self.db.execute(
            select(func.count(InventoryReservation.id)).where(
                InventoryReservation.warehouse_id == warehouse_id,
                InventoryReservation.status.in_([
                    ReservationStatus.ACTIVE, ReservationStatus.PENDING,
                ]),
            )
        )
        reservation_count = reservation_result.scalar() or 0

        # Capacity
        capacity = await self.capacity_service.get_capacity(warehouse_id)

        total_available = warehouse_agg.get("total_available", 0)
        total_reserved = warehouse_agg.get("total_reserved", 0)
        total_incoming = warehouse_agg.get("total_incoming", 0)
        total_damaged = warehouse_agg.get("total_damaged", 0)

        result = {
            "warehouse_id": str(warehouse_id),
            "warehouse_name": warehouse.name,
            "warehouse_code": warehouse.code,
            "available_stock": total_available,
            "reserved_stock": total_reserved,
            "incoming_stock": total_incoming,
            "damaged_stock": total_damaged,
            "total_stock": total_available + total_reserved + total_incoming + total_damaged,
            "allocated_stock": reservation_count,
            "sku_count": sku_count,
            "variant_count": warehouse_agg.get("variant_count", 0),
            "product_count": warehouse_agg.get("product_count", 0),
            "capacity_used": capacity.get("current_usage", 0),
            "capacity_remaining": capacity.get("available_capacity"),
            "capacity_percentage": capacity.get("usage_percentage"),
            "capacity_status": capacity.get("status", "normal"),
        }

        await self.cache.set(cache_key, result, ttl=60)
        return result

    # ═══════════════════════════════════════════════════════════════
    # F.5 — STORE AGGREGATION
    # ═══════════════════════════════════════════════════════════════

    async def get_store(self) -> dict:
        """
        Aggregate inventory for the entire store.
        """
        # Check cache first
        cache_key = InventoryAggregationCache.key_store(self.store.id)
        cached = await self.cache.get(cache_key)
        if cached is not None:
            return cached

        wh_ids = await self._get_active_warehouse_ids()
        if not wh_ids:
            empty = self._empty_store()
            await self.cache.set(cache_key, empty, ttl=30)
            return empty

        # ── Total stock across all warehouses (using repository) ──
        store_agg = await self.inv_repo.aggregate_store(wh_ids)

        # ── Inventory value (estimated) ──
        inventory_value = await self.inv_repo.aggregate_inventory_value(wh_ids)

        # ── Counts ──
        wh_count = len(wh_ids)
        total_products = store_agg.get("product_count", 0)
        total_variants = store_agg.get("variant_count", 0)

        # ── Reservations ──
        reservation_result = await self.db.execute(
            select(func.count(InventoryReservation.id)).where(
                InventoryReservation.store_id == self.store.id,
                InventoryReservation.status.in_([
                    ReservationStatus.ACTIVE, ReservationStatus.PENDING,
                ]),
            )
        )
        reservation_count = reservation_result.scalar() or 0

        # ── In-transit transfers ──
        in_transit_count = await self.transfer_repo.count_by_status(
            self.store.id, TransferStatus.IN_TRANSIT,
        )

        # ── Top 5 warehouses by available stock ──
        top_wh_result = await self.db.execute(
            select(
                WarehouseInventory.warehouse_id,
                func.coalesce(func.sum(WarehouseInventory.available_stock), 0).label("stock"),
            )
            .where(WarehouseInventory.warehouse_id.in_(wh_ids))
            .group_by(WarehouseInventory.warehouse_id)
            .order_by(func.sum(WarehouseInventory.available_stock).desc())
            .limit(5)
        )
        wh_map = await self._get_warehouse_name_map(wh_ids)
        top_warehouses = []
        for tw in top_wh_result.all():
            wh_id_str = str(tw.warehouse_id)
            top_warehouses.append({
                "warehouse_id": wh_id_str,
                "warehouse_name": wh_map.get(wh_id_str, "Unknown"),
                "available_stock": tw.stock or 0,
            })

        # ── Lowest stock products (top 5 by total available) ──
        low_stock_result = await self.db.execute(
            select(
                WarehouseInventory.product_id,
                func.coalesce(func.sum(WarehouseInventory.available_stock), 0).label("stock"),
                func.count(func.distinct(WarehouseInventory.variant_id)).label("variants"),
            )
            .where(
                WarehouseInventory.warehouse_id.in_(wh_ids),
                WarehouseInventory.product_id.isnot(None),
            )
            .group_by(WarehouseInventory.product_id)
            .order_by(func.sum(WarehouseInventory.available_stock).asc())
            .limit(5)
        )
        low_stock_rows = low_stock_result.all()
        low_stock_ids = [r.product_id for r in low_stock_rows if r.product_id]
        product_titles = await self._batch_product_titles(low_stock_ids)
        lowest_stock = []
        for ls in low_stock_rows:
            pid_str = str(ls.product_id) if ls.product_id else ""
            lowest_stock.append({
                "product_id": pid_str,
                "product_title": product_titles.get(pid_str, "Unknown"),
                "available_stock": ls.stock or 0,
                "variant_count": ls.variants or 0,
            })

        # ── Most reserved products (top 5) ──
        most_reserved_result = await self.db.execute(
            select(
                InventoryReservation.product_id,
                func.coalesce(func.sum(InventoryReservation.quantity), 0).label("reserved_qty"),
                func.count(InventoryReservation.id).label("reservation_count"),
            )
            .where(
                InventoryReservation.store_id == self.store.id,
                InventoryReservation.status.in_([
                    ReservationStatus.ACTIVE, ReservationStatus.PENDING,
                ]),
                InventoryReservation.product_id.isnot(None),
            )
            .group_by(InventoryReservation.product_id)
            .order_by(func.sum(InventoryReservation.quantity).desc())
            .limit(5)
        )
        most_reserved_rows = most_reserved_result.all()
        reserved_ids = [r.product_id for r in most_reserved_rows if r.product_id]
        reserved_titles = await self._batch_product_titles(reserved_ids)
        most_reserved = []
        for mr in most_reserved_rows:
            pid_str = str(mr.product_id) if mr.product_id else ""
            most_reserved.append({
                "product_id": pid_str,
                "product_title": reserved_titles.get(pid_str, "Unknown"),
                "reserved_quantity": mr.reserved_qty or 0,
                "reservation_count": mr.reservation_count or 0,
            })

        # ── Warehouse utilization — BATCHED single GROUP BY query ──
        # Eliminates N+1: was looping wh_ids calling capacity_service.get_capacity() per warehouse.
        # Now: single SQL aggregate + single warehouse info query.
        warehouse_utilization = []
        if wh_ids:
            # Get all warehouse capacity data + names in TWO batch queries
            capacity_data = await self.inv_repo.aggregate_capacity(wh_ids)
            wh_map_full = await self._get_warehouse_name_map(wh_ids)

            # Get all warehouse capacity limits in a single batch query
            wh_capacity_result = await self.db.execute(
                select(Warehouse.id, Warehouse.capacity, Warehouse.capacity_unit).where(
                    Warehouse.id.in_(wh_ids),
                )
            )
            wh_capacity_map = {
                str(r[0]): {"capacity": r[1], "capacity_unit": r[2]}
                for r in wh_capacity_result.all()
            }

            for wh_id in wh_ids:
                wh_id_str = str(wh_id)
                cap_info = capacity_data.get(wh_id_str, {})
                wh_cap = wh_capacity_map.get(wh_id_str, {})
                total_usage = cap_info.get("total_stock", 0)
                capacity_limit = wh_cap.get("capacity")

                usage_pct = round(
                    (total_usage / capacity_limit * 100), 1
                ) if capacity_limit and capacity_limit > 0 else None

                status = "normal"
                if usage_pct is not None:
                    if usage_pct >= 95:
                        status = "critical"
                    elif usage_pct >= 80:
                        status = "warning"
                    elif usage_pct >= 100:
                        status = "exceeded"

                warehouse_utilization.append({
                    "warehouse_id": wh_id_str,
                    "warehouse_name": wh_map_full.get(wh_id_str, "Unknown"),
                    "capacity": capacity_limit,
                    "current_usage": total_usage,
                    "usage_percentage": usage_pct,
                    "status": status,
                })

        total_available = store_agg.get("total_available", 0)
        total_reserved = store_agg.get("total_reserved", 0)
        total_incoming = store_agg.get("total_incoming", 0)
        total_damaged = store_agg.get("total_damaged", 0)

        result = {
            "store_id": str(self.store.id),
            "total_available_stock": total_available,
            "total_reserved_stock": total_reserved,
            "total_incoming_stock": total_incoming,
            "total_damaged_stock": total_damaged,
            "total_stock": total_available + total_reserved + total_incoming + total_damaged,
            "inventory_value": round(inventory_value, 2),
            "warehouse_count": wh_count,
            "product_count": total_products,
            "variant_count": total_variants,
            "reservation_count": reservation_count,
            "transfer_in_transit_count": in_transit_count,
            "top_warehouses": top_warehouses,
            "lowest_stock_products": lowest_stock,
            "most_reserved_products": most_reserved,
            "warehouse_utilization": warehouse_utilization,
        }

        await self.cache.set(cache_key, result, ttl=60)
        return result

    # ═══════════════════════════════════════════════════════════════
    # F.6 — DASHBOARD INTEGRATION
    # ═══════════════════════════════════════════════════════════════

    async def get_dashboard(self) -> dict:
        """
        Dashboard summary — quick aggregation for frontend widgets.

        Uses COUNT queries for all counts (no row loading).
        """
        # Check cache first
        cache_key = InventoryAggregationCache.key_dashboard(self.store.id)
        cached = await self.cache.get(cache_key)
        if cached is not None:
            return cached

        wh_ids = await self._get_active_warehouse_ids()

        # Use repository aggregate for dashboard-level data
        dashboard_data = await self.inv_repo.aggregate_dashboard(wh_ids)

        # Warehouse count
        wh_count = len(wh_ids)
        active_wh = await self.wh_repo.count_active(self.store.id)

        # Reservation counts
        active_res = await self.db.execute(
            select(func.count(InventoryReservation.id)).where(
                InventoryReservation.store_id == self.store.id,
                InventoryReservation.status.in_([
                    ReservationStatus.ACTIVE, ReservationStatus.PENDING,
                ]),
            )
        )

        # In-transit transfers
        in_transit = await self.transfer_repo.count_by_status(
            self.store.id, TransferStatus.IN_TRANSIT,
        )

        result = {
            "total_available_inventory": dashboard_data.get("total_available", 0),
            "total_reserved_inventory": dashboard_data.get("total_reserved", 0),
            "total_incoming_inventory": dashboard_data.get("total_incoming", 0),
            "total_damaged_inventory": dashboard_data.get("total_damaged", 0),
            "inventory_value": round(dashboard_data.get("inventory_value", 0.0), 2),
            "warehouse_count": wh_count,
            "active_warehouse_count": active_wh,
            "active_reservations": active_res.scalar() or 0,
            "transfer_in_transit_count": in_transit,
        }

        await self.cache.set(cache_key, result, ttl=60)
        return result

    # ═══════════════════════════════════════════════════════════════
    # F.7 — DISTRIBUTION ENDPOINT
    # ═══════════════════════════════════════════════════════════════

    async def get_distribution(self, variant_id: uuid.UUID) -> dict:
        """
        Get stock distribution for a variant across all warehouses.

        Returns per-warehouse breakdown with percentages.
        """
        # Check cache first
        cache_key = InventoryAggregationCache.key_distribution(self.store.id, variant_id)
        cached = await self.cache.get(cache_key)
        if cached is not None:
            return cached

        variant_data = await self.get_variant(variant_id)
        if not variant_data.get("warehouse_breakdown"):
            result = {
                "variant_id": str(variant_id),
                "total_stock": 0,
                "warehouses": [],
            }
            await self.cache.set(cache_key, result, ttl=30)
            return result

        total = variant_data["total_stock"]
        warehouses = []
        for w in variant_data["warehouse_breakdown"]:
            pct = round((w["total"] / total * 100), 1) if total > 0 else 0
            warehouses.append({
                **w,
                "percentage": pct,
            })

        result = {
            "variant_id": str(variant_id),
            "sku": variant_data.get("sku"),
            "title": variant_data.get("title"),
            "total_stock": total,
            "warehouses": sorted(warehouses, key=lambda x: x["total"], reverse=True),
        }

        await self.cache.set(cache_key, result, ttl=30)
        return result

    # ═══════════════════════════════════════════════════════════════
    # F.11 — REPORT DATA
    # ═══════════════════════════════════════════════════════════════

    async def get_report_data(self) -> dict:
        """
        Aggregation data required by inventory reports.

        Optimized: all per-warehouse queries use GROUP BY (no N+1 loops).
        """
        # Check cache first
        cache_key = InventoryAggregationCache.key_reports(self.store.id)
        cached = await self.cache.get(cache_key)
        if cached is not None:
            return cached

        wh_ids = await self._get_active_warehouse_ids()
        wh_map = await self._get_warehouse_name_map(wh_ids)

        if wh_ids:
            # ── Inventory value per warehouse — SINGLE GROUP BY query ──
            # Eliminates N+1: was looping wh_ids calling db.execute() per warehouse
            value_by_wh_result = await self.db.execute(
                select(
                    WarehouseInventory.warehouse_id,
                    func.coalesce(
                        func.sum(WarehouseInventory.available_stock * ProductVariant.price), 0
                    ).label("inventory_value"),
                )
                .select_from(WarehouseInventory)
                .join(ProductVariant, WarehouseInventory.variant_id == ProductVariant.id)
                .where(WarehouseInventory.warehouse_id.in_(wh_ids))
                .group_by(WarehouseInventory.warehouse_id)
            )
            value_by_wh = []
            for v_row in value_by_wh_result.all():
                wh_id_str = str(v_row.warehouse_id)
                value_by_wh.append({
                    "warehouse_id": wh_id_str,
                    "warehouse_name": wh_map.get(wh_id_str, "Unknown"),
                    "inventory_value": round(float(v_row.inventory_value or 0), 2),
                })

            # Add warehouses with no inventory value (zero)
            valued_wh_ids = {v["warehouse_id"] for v in value_by_wh}
            for wh_id in wh_ids:
                wh_id_str = str(wh_id)
                if wh_id_str not in valued_wh_ids:
                    value_by_wh.append({
                        "warehouse_id": wh_id_str,
                        "warehouse_name": wh_map.get(wh_id_str, "Unknown"),
                        "inventory_value": 0.0,
                    })

            # Fast movers (top 10 by available stock)
            fast_result = await self.db.execute(
                select(
                    WarehouseInventory.variant_id,
                    func.coalesce(func.sum(WarehouseInventory.available_stock), 0).label("stock"),
                )
                .where(
                    WarehouseInventory.warehouse_id.in_(wh_ids),
                    WarehouseInventory.available_stock > 0,
                )
                .group_by(WarehouseInventory.variant_id)
                .order_by(func.sum(WarehouseInventory.available_stock).desc())
                .limit(10)
            )
            fast_rows = fast_result.all()
            fast_ids = [r.variant_id for r in fast_rows]
            fast_info = await self._batch_variant_info(fast_ids)
            fast_movers = [
                {
                    "variant_id": str(fm.variant_id),
                    "sku": fast_info.get(str(fm.variant_id), {}).get("sku"),
                    "title": fast_info.get(str(fm.variant_id), {}).get("title"),
                    "available_stock": fm.stock or 0,
                }
                for fm in fast_rows
            ]

            # Slow movers (bottom 10 with stock, but low)
            slow_result = await self.db.execute(
                select(
                    WarehouseInventory.variant_id,
                    func.coalesce(func.sum(WarehouseInventory.available_stock), 0).label("stock"),
                )
                .where(
                    WarehouseInventory.warehouse_id.in_(wh_ids),
                    WarehouseInventory.available_stock > 0,
                )
                .group_by(WarehouseInventory.variant_id)
                .order_by(func.sum(WarehouseInventory.available_stock).asc())
                .limit(10)
            )
            slow_rows = slow_result.all()
            slow_ids = [r.variant_id for r in slow_rows]
            slow_info = await self._batch_variant_info(slow_ids)
            slow_movers = [
                {
                    "variant_id": str(sm.variant_id),
                    "sku": slow_info.get(str(sm.variant_id), {}).get("sku"),
                    "title": slow_info.get(str(sm.variant_id), {}).get("title"),
                    "available_stock": sm.stock or 0,
                }
                for sm in slow_rows
            ]

            # Dead stock count
            dead_result = await self.db.execute(
                select(func.count(func.distinct(WarehouseInventory.variant_id)))
                .where(
                    WarehouseInventory.warehouse_id.in_(wh_ids),
                    WarehouseInventory.available_stock == 0,
                    WarehouseInventory.reserved_stock == 0,
                )
            )
            dead_stock_count = dead_result.scalar() or 0
        else:
            value_by_wh = []
            fast_movers = []
            slow_movers = []
            dead_stock_count = 0

        result = {
            "inventory_value_by_warehouse": value_by_wh,
            "fast_movers": fast_movers,
            "slow_movers": slow_movers,
            "dead_stock_count": dead_stock_count,
        }

        await self.cache.set(cache_key, result, ttl=60)
        return result

    # ═══════════════════════════════════════════════════════════════
    # CACHE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def invalidate_cache(self) -> int:
        """
        Invalidate ALL cached aggregation data for the current store.

        Called by external services after inventory-changing operations:
        - Reservation created/released/committed
        - Allocation
        - Transfer
        - WooCommerce Sync
        - Manual Inventory Update

        Returns count of cleared entries.
        """
        return await self.cache.invalidate_store(self.store.id)

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ═══════════════════════════════════════════════════════════════

    async def _get_active_warehouse_ids(self) -> list[uuid.UUID]:
        """Get IDs of all active warehouses for the current store."""
        result = await self.db.execute(
            select(Warehouse.id).where(
                Warehouse.store_id == self.store.id,
                Warehouse.is_active == True,
            )
        )
        rows = result.all()
        return [r[0] for r in rows] if rows else []

    async def _get_warehouse_name_map(self, wh_ids: list[uuid.UUID]) -> dict[str, str]:
        """Get a mapping of warehouse ID -> name."""
        if not wh_ids:
            return {}
        result = await self.db.execute(
            select(Warehouse.id, Warehouse.name).where(
                Warehouse.id.in_(wh_ids),
            )
        )
        return {str(r[0]): r[1] for r in result.all()}

    async def _batch_product_titles(self, product_ids: list[uuid.UUID]) -> dict[str, str]:
        """Batch get product titles for a list of product IDs."""
        if not product_ids:
            return {}
        result = await self.db.execute(
            select(Product.id, Product.title).where(Product.id.in_(set(product_ids)))
        )
        return {str(r[0]): r[1] or "Unknown" for r in result.all()}

    async def _batch_variant_info(
        self, variant_ids: list[uuid.UUID],
    ) -> dict[str, dict]:
        """Batch get variant SKU and title for a list of variant IDs."""
        if not variant_ids:
            return {}
        result = await self.db.execute(
            select(ProductVariant.id, ProductVariant.sku, ProductVariant.title).where(
                ProductVariant.id.in_(set(variant_ids)),
            )
        )
        return {
            str(r[0]): {"sku": r[1], "title": r[2]}
            for r in result.all()
        }

    def _empty_variant(self, variant_id: uuid.UUID) -> dict:
        return {
            "variant_id": str(variant_id),
            "product_id": None,
            "sku": None,
            "title": None,
            "total_stock": 0,
            "available_stock": 0,
            "reserved_stock": 0,
            "incoming_stock": 0,
            "damaged_stock": 0,
            "allocated_stock": 0,
            "in_transit_stock": 0,
            "warehouse_count": 0,
            "warehouse_breakdown": [],
        }

    def _empty_product(self, product_id: uuid.UUID, variant_count: int = 0) -> dict:
        return {
            "product_id": str(product_id),
            "title": None,
            "total_available": 0,
            "total_reserved": 0,
            "total_incoming": 0,
            "total_damaged": 0,
            "variant_count": variant_count,
            "warehouse_count": 0,
            "variant_breakdown": [],
        }

    def _empty_store(self) -> dict:
        return {
            "store_id": str(self.store.id),
            "total_available_stock": 0,
            "total_reserved_stock": 0,
            "total_incoming_stock": 0,
            "total_damaged_stock": 0,
            "total_stock": 0,
            "inventory_value": 0.0,
            "warehouse_count": 0,
            "product_count": 0,
            "variant_count": 0,
            "reservation_count": 0,
            "transfer_in_transit_count": 0,
            "top_warehouses": [],
            "lowest_stock_products": [],
            "most_reserved_products": [],
            "warehouse_utilization": [],
        }
