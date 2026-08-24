"""
Store-centric Inventory Aggregation Engine.

Aggregates inventory at the store level (single-location SaaS model):

- Available stock comes from ProductVariant.inventory_quantity
- Reserved / committed stock comes from the inventory_reservations table
- Values are computed from variant price × quantity

Aggregation scopes:
- get_store()    — whole-store totals
- get_product()  — a product across all its variants
- get_variant()  — a single variant
- get_dashboard()— quick widget summary
- get_report_data() — store-level report data

All scopes validate store ownership. Results are cached via
app.inventory.aggregation_cache and invalidated on any inventory change.
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models import Store, Product, ProductVariant, InventoryReservation
from app.inventory.constants import ReservationStatus
from app.inventory.aggregation_cache import aggregation_cache
from app.inventory.exceptions import InvalidStoreOwnershipError

logger = logging.getLogger(__name__)


class InventoryAggregationEngine:
    """Aggregates store inventory for dashboards and reports."""

    def __init__(
        self,
        db: AsyncSession,
        store: Store,
        user_id: Optional[uuid.UUID] = None,
    ):
        self.db = db
        self.store = store
        self.user_id = user_id
        self.logger = logging.getLogger(f"{__name__}.InventoryAggregationEngine")

    # ═══════════════════════════════════════════════════════════════
    # STORE AGGREGATION
    # ═══════════════════════════════════════════════════════════════

    async def get_store(self, use_cache: bool = True) -> dict:
        """Aggregate inventory for the entire store."""
        cache_key = aggregation_cache.key_store(self.store.id)
        if use_cache:
            cached = await aggregation_cache.get(cache_key)
            if cached is not None:
                return cached

        result = await self._compute_store_totals()
        await aggregation_cache.set(cache_key, result)
        return result

    async def get_dashboard(self, use_cache: bool = True) -> dict:
        """Dashboard summary for frontend widgets."""
        cache_key = aggregation_cache.key_dashboard(self.store.id)
        if use_cache:
            cached = await aggregation_cache.get(cache_key)
            if cached is not None:
                return cached

        totals = await self._compute_store_totals()
        result = {
            "total_available_inventory": totals["total_available_inventory"],
            "total_reserved_inventory": totals["total_reserved_inventory"],
            "inventory_value": float(totals["inventory_value"]),
            "low_stock_variants": totals["low_stock_variant_count"],
            "out_of_stock_variants": totals["out_of_stock_variant_count"],
            "active_reservations": totals["active_reservations_count"],
            "product_count": totals["product_count"],
            "variant_count": totals["variant_count"],
            "store_id": str(self.store.id),
        }
        await aggregation_cache.set(cache_key, result)
        return result

    # ═══════════════════════════════════════════════════════════════
    # PRODUCT / VARIANT AGGREGATION
    # ═══════════════════════════════════════════════════════════════

    async def get_product(self, product_id: uuid.UUID, use_cache: bool = True) -> dict:
        """Aggregate inventory for a product across all its variants."""
        product = await self._get_product(product_id)
        if product is None:
            from app.inventory.exceptions import ProductNotFoundError
            raise ProductNotFoundError(str(product_id))
        self._ensure_store_owns_product(product)

        cache_key = aggregation_cache.key_product(self.store.id, product_id)
        if use_cache:
            cached = await aggregation_cache.get(cache_key)
            if cached is not None:
                return cached

        variants = product.variants
        reserved = await self._reserved_units_for_variants(
            [v.id for v in variants]
        )
        committed = await self._committed_units_for_variants(
            [v.id for v in variants]
        )
        reserved_by_variant = await self._reserved_units_by_variant(
            [v.id for v in variants]
        )

        available = sum(v.inventory_quantity for v in variants)
        inventory_value = sum(
            (v.price or Decimal("0.00")) * v.inventory_quantity for v in variants
        )

        result = {
            "product_id": str(product.id),
            "title": product.title,
            "store_id": str(self.store.id),
            "total_available_inventory": available,
            "total_reserved_inventory": reserved,
            "total_committed_inventory": committed,
            "inventory_value": float(inventory_value),
            "variant_count": len(variants),
            "variants": [
                {
                    "variant_id": str(v.id),
                    "title": v.title,
                    "sku": v.sku,
                    "available_quantity": v.inventory_quantity,
                    "reserved_quantity": reserved_by_variant.get(str(v.id), 0),
                    "inventory_value": float((v.price or Decimal("0.00")) * v.inventory_quantity),
                }
                for v in variants
            ],
        }
        await aggregation_cache.set(cache_key, result)
        return result

    async def get_variant(self, variant_id: uuid.UUID, use_cache: bool = True) -> dict:
        """Aggregate inventory for a single variant."""
        variant = await self._get_variant(variant_id)
        if variant is None:
            from app.inventory.exceptions import VariantNotFoundError
            raise VariantNotFoundError(str(variant_id))
        self._ensure_store_owns_variant(variant)

        cache_key = aggregation_cache.key_variant(self.store.id, variant_id)
        if use_cache:
            cached = await aggregation_cache.get(cache_key)
            if cached is not None:
                return cached

        reserved = await self._reserved_units_for_variants([variant.id])
        committed = await self._committed_units_for_variants([variant.id])

        available = variant.inventory_quantity
        threshold = variant.low_stock_threshold or 10
        if available <= 0:
            status = "out_of_stock"
        elif available <= threshold:
            status = "low_stock"
        else:
            status = "in_stock"

        result = {
            "variant_id": str(variant.id),
            "product_id": str(variant.product_id),
            "sku": variant.sku,
            "title": variant.title,
            "available_quantity": available,
            "reserved_quantity": reserved,
            "committed_quantity": committed,
            "total_quantity": available + reserved + committed,
            "low_stock_threshold": threshold,
            "status": status,
            "inventory_value": float((variant.price or Decimal("0.00")) * available),
        }
        await aggregation_cache.set(cache_key, result)
        return result

    # ═══════════════════════════════════════════════════════════════
    # REPORTS
    # ═══════════════════════════════════════════════════════════════

    async def get_report_data(self, use_cache: bool = True) -> dict:
        """Store-level inventory report data."""
        cache_key = aggregation_cache.key_reports(self.store.id)
        if use_cache:
            cached = await aggregation_cache.get(cache_key)
            if cached is not None:
                return cached

        totals = await self._compute_store_totals()

        # All variants of the store for movers/dead-stock analysis
        variants_result = await self.db.execute(
            select(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .join(Product)
            .where(Product.store_id == self.store.id)
        )
        variants = list(variants_result.scalars().all())

        ranked = sorted(variants, key=lambda v: v.inventory_quantity, reverse=True)

        result = {
            "store_id": str(self.store.id),
            "total_inventory_value": float(totals["inventory_value"]),
            "total_available_inventory": totals["total_available_inventory"],
            "total_reserved_inventory": totals["total_reserved_inventory"],
            "fast_movers": [
                {
                    "variant_id": str(v.id),
                    "sku": v.sku,
                    "product_title": v.product.title if v.product else "N/A",
                    "available_quantity": v.inventory_quantity,
                }
                for v in ranked[:10]
            ],
            "slow_movers": [
                {
                    "variant_id": str(v.id),
                    "sku": v.sku,
                    "product_title": v.product.title if v.product else "N/A",
                    "available_quantity": v.inventory_quantity,
                }
                for v in ranked[-10:]
            ],
            "dead_stock_count": sum(
                1 for v in variants if v.inventory_quantity <= 0
            ),
        }
        await aggregation_cache.set(cache_key, result)
        return result

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ═══════════════════════════════════════════════════════════════

    async def _compute_store_totals(self) -> dict:
        """Compute whole-store aggregation totals in one pass."""
        variant_result = await self.db.execute(
            select(
                func.count(ProductVariant.id),
                func.coalesce(func.sum(ProductVariant.inventory_quantity), 0),
                func.coalesce(
                    func.sum(ProductVariant.inventory_quantity * ProductVariant.price), 0
                ),
            )
            .select_from(ProductVariant)
            .join(Product)
            .where(Product.store_id == self.store.id)
        )
        variant_count, available, value = variant_result.one()
        variant_count = variant_count or 0
        available = int(available or 0)
        value = Decimal(value or 0)

        product_count_result = await self.db.execute(
            select(func.count(Product.id)).where(Product.store_id == self.store.id)
        )
        product_count = product_count_result.scalar() or 0

        active_conditions = [
            InventoryReservation.store_id == self.store.id,
            InventoryReservation.status.in_(
                [ReservationStatus.ACTIVE, ReservationStatus.PENDING]
            ),
        ]
        reserved_result = await self.db.execute(
            select(func.coalesce(func.sum(InventoryReservation.quantity), 0)).where(
                *active_conditions,
            )
        )
        reserved = int(reserved_result.scalar() or 0)

        active_count_result = await self.db.execute(
            select(func.count(InventoryReservation.id)).where(*active_conditions)
        )
        active_count = active_count_result.scalar() or 0

        threshold_result = await self.db.execute(
            select(func.count(ProductVariant.id))
            .select_from(ProductVariant)
            .join(Product)
            .where(
                Product.store_id == self.store.id,
                ProductVariant.inventory_quantity <= func.coalesce(
                    ProductVariant.low_stock_threshold, 10
                ),
                ProductVariant.inventory_quantity > 0,
            )
        )
        low_stock_count = threshold_result.scalar() or 0

        out_result = await self.db.execute(
            select(func.count(ProductVariant.id))
            .select_from(ProductVariant)
            .join(Product)
            .where(
                Product.store_id == self.store.id,
                ProductVariant.inventory_quantity <= 0,
            )
        )
        out_of_stock_count = out_result.scalar() or 0

        return {
            "store_id": str(self.store.id),
            "total_available_inventory": available,
            "total_reserved_inventory": reserved,
            "inventory_value": value,
            "product_count": product_count,
            "variant_count": variant_count,
            "low_stock_variant_count": low_stock_count,
            "out_of_stock_variant_count": out_of_stock_count,
            "active_reservations_count": active_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _reserved_units_for_variants(self, variant_ids: list[uuid.UUID]) -> int:
        if not variant_ids:
            return 0
        result = await self.db.execute(
            select(func.coalesce(func.sum(InventoryReservation.quantity), 0)).where(
                InventoryReservation.store_id == self.store.id,
                InventoryReservation.variant_id.in_(variant_ids),
                InventoryReservation.status.in_(
                    [ReservationStatus.ACTIVE, ReservationStatus.PENDING]
                ),
            )
        )
        return int(result.scalar() or 0)

    async def _committed_units_for_variants(self, variant_ids: list[uuid.UUID]) -> int:
        if not variant_ids:
            return 0
        result = await self.db.execute(
            select(func.coalesce(func.sum(InventoryReservation.quantity), 0)).where(
                InventoryReservation.store_id == self.store.id,
                InventoryReservation.variant_id.in_(variant_ids),
                InventoryReservation.status == ReservationStatus.COMMITTED,
            )
        )
        return int(result.scalar() or 0)

    async def _reserved_units_by_variant(
        self, variant_ids: list[uuid.UUID],
    ) -> dict[str, int]:
        """Reserved units keyed by variant id (string)."""
        if not variant_ids:
            return {}
        result = await self.db.execute(
            select(
                InventoryReservation.variant_id,
                func.coalesce(func.sum(InventoryReservation.quantity), 0),
            ).where(
                InventoryReservation.store_id == self.store.id,
                InventoryReservation.variant_id.in_(variant_ids),
                InventoryReservation.status.in_(
                    [ReservationStatus.ACTIVE, ReservationStatus.PENDING]
                ),
            ).group_by(InventoryReservation.variant_id)
        )
        return {str(variant_id): int(qty or 0) for variant_id, qty in result.all()}

    async def _get_product(self, product_id: uuid.UUID) -> Optional[Product]:
        result = await self.db.execute(
            select(Product)
            .options(selectinload(Product.variants))
            .where(Product.id == product_id)
        )
        return result.scalar_one_or_none()

    async def _get_variant(self, variant_id: uuid.UUID) -> Optional[ProductVariant]:
        result = await self.db.execute(
            select(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .where(ProductVariant.id == variant_id)
        )
        return result.scalar_one_or_none()

    def _ensure_store_owns_product(self, product: Product) -> None:
        if str(product.store_id) != str(self.store.id):
            raise InvalidStoreOwnershipError("Product", str(product.id))

    def _ensure_store_owns_variant(self, variant: ProductVariant) -> None:
        if variant.product and str(variant.product.store_id) != str(self.store.id):
            raise InvalidStoreOwnershipError("Variant", str(variant.id))
