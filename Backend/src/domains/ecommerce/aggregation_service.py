# ═══════════════════════════════════════════════════════════════
# domains / ecommerce / aggregation_service.py
#
# PURPOSE: Inventory aggregation — store / product / variant
#          level stock numbers (available, reserved, committed,
#          value) aur report (movers, dead stock).
#
# USED BY: domains/ecommerce/aggregation_routes.py
#
# NOTE:    Ported from kulsoom (backend-fte/app/inventory/
#          aggregation_engine.py). Cache hata diya — queries
#          chhoti aggregate SQL hain, live compute hoti hain.
#          Changes vs kulsoom:
#            - fast/slow movers ab asli sales (OrderItem, last N
#              days) se, kulsoom mein sirf stock ke hisaab se thay
#            - dead stock = stock hai lekin N din mein sale nahi
#              (kulsoom mein dead stock = out of stock tha)
# ═══════════════════════════════════════════════════════════════

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.sdk.exceptions import AgentError
from src.sdk.models.base import Product, Variant, Order, OrderItem
from src.sdk.models.inventory import StockReservation, RESERVATION_ACTIVE, RESERVATION_COMMITTED

DEFAULT_THRESHOLD = 10


def _stock_status(available: int, threshold: Optional[int]) -> str:
    threshold = threshold if threshold is not None else DEFAULT_THRESHOLD
    if available <= 0:
        return "out_of_stock"
    if available <= threshold:
        return "low_stock"
    return "in_stock"


class AggregationService:
    """Read-only inventory numbers scoped to one store."""

    def __init__(self, db: AsyncSession, store_id: int):
        self.db = db
        self.store_id = store_id

    # ─── Reservation sums ───────────────────────────────────────

    async def _reserved_by_variant(self, status: str, variant_ids: Optional[list[int]] = None) -> dict[int, int]:
        conditions = [StockReservation.store_id == self.store_id, StockReservation.status == status]
        if variant_ids is not None:
            if not variant_ids:
                return {}
            conditions.append(StockReservation.variant_id.in_(variant_ids))
        rows = (await self.db.execute(
            select(StockReservation.variant_id, func.coalesce(func.sum(StockReservation.quantity), 0))
            .where(*conditions)
            .group_by(StockReservation.variant_id)
        )).all()
        return {vid: int(q) for vid, q in rows}

    # ─── Store summary ──────────────────────────────────────────

    async def get_store_summary(self) -> dict:
        available, variant_count, value, low, out = (await self.db.execute(
            select(
                func.coalesce(func.sum(Variant.inventory_quantity), 0),
                func.count(Variant.id),
                func.coalesce(func.sum(Variant.inventory_quantity * Variant.price), 0),
                func.count(Variant.id).filter(
                    Variant.inventory_quantity > 0,
                    Variant.inventory_quantity <= func.coalesce(Variant.low_stock_threshold, DEFAULT_THRESHOLD),
                ),
                func.count(Variant.id).filter(Variant.inventory_quantity <= 0),
            )
            .select_from(Variant)
            .join(Product, Product.id == Variant.product_id)
            .where(Product.store_id == self.store_id)
        )).one()

        product_count = (await self.db.execute(
            select(func.count(Product.id)).where(Product.store_id == self.store_id)
        )).scalar() or 0

        reserved = await self._reserved_by_variant(RESERVATION_ACTIVE)
        active_reservations = (await self.db.execute(
            select(func.count(StockReservation.id)).where(
                StockReservation.store_id == self.store_id, StockReservation.status == RESERVATION_ACTIVE
            )
        )).scalar() or 0

        return {
            "store_id": self.store_id,
            "product_count": product_count,
            "variant_count": variant_count,
            "total_available_units": int(available),
            "total_reserved_units": sum(reserved.values()),
            "inventory_value": float(Decimal(value or 0)),
            "low_stock_variants": low,
            "out_of_stock_variants": out,
            "active_reservations": active_reservations,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ─── Product ────────────────────────────────────────────────

    async def get_product(self, product_id: int) -> dict:
        result = await self.db.execute(
            select(Product).where(Product.id == product_id, Product.store_id == self.store_id)
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise AgentError(f"Product {product_id} not found in this store", code=404)

        variants = (await self.db.execute(
            select(Variant).where(Variant.product_id == product_id).order_by(Variant.id)
        )).scalars().all()
        ids = [v.id for v in variants]
        reserved = await self._reserved_by_variant(RESERVATION_ACTIVE, ids)
        committed = await self._reserved_by_variant(RESERVATION_COMMITTED, ids)

        def value(v: Variant) -> float:
            return float((v.price or Decimal(0)) * (v.inventory_quantity or 0))

        return {
            "product_id": product.id,
            "title": product.title,
            "store_id": self.store_id,
            "variant_count": len(variants),
            "total_available_units": sum(v.inventory_quantity or 0 for v in variants),
            "total_reserved_units": sum(reserved.values()),
            "total_committed_units": sum(committed.values()),
            "inventory_value": sum(value(v) for v in variants),
            "variants": [
                {
                    "variant_id": v.id,
                    "title": v.title,
                    "sku": v.sku,
                    "available_quantity": v.inventory_quantity or 0,
                    "reserved_quantity": reserved.get(v.id, 0),
                    "committed_quantity": committed.get(v.id, 0),
                    "status": _stock_status(v.inventory_quantity or 0, v.low_stock_threshold),
                    "inventory_value": value(v),
                }
                for v in variants
            ],
        }

    # ─── Variant ────────────────────────────────────────────────

    async def get_variant(self, variant_id: int) -> dict:
        result = await self.db.execute(
            select(Variant)
            .join(Product, Product.id == Variant.product_id)
            .where(Variant.id == variant_id, Product.store_id == self.store_id)
        )
        v = result.scalar_one_or_none()
        if v is None:
            raise AgentError(f"Variant {variant_id} not found in this store", code=404)

        reserved = (await self._reserved_by_variant(RESERVATION_ACTIVE, [v.id])).get(v.id, 0)
        committed = (await self._reserved_by_variant(RESERVATION_COMMITTED, [v.id])).get(v.id, 0)
        available = v.inventory_quantity or 0
        threshold = v.low_stock_threshold if v.low_stock_threshold is not None else DEFAULT_THRESHOLD

        return {
            "variant_id": v.id,
            "product_id": v.product_id,
            "sku": v.sku,
            "title": v.title,
            "available_quantity": available,
            "reserved_quantity": reserved,
            "committed_quantity": committed,
            "on_hand_quantity": available + reserved,   # reserved abhi physically store mein hai
            "low_stock_threshold": threshold,
            "status": _stock_status(available, threshold),
            "inventory_value": float((v.price or Decimal(0)) * available),
        }

    # ─── Report ─────────────────────────────────────────────────

    async def get_report(self, days: int = 30, limit: int = 10) -> dict:
        """Sales-based movers: units sold in last `days` days (non-cancelled/any order)."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        summary = await self.get_store_summary()

        sold_rows = await self._sold_in_window(since)

        def row(r) -> dict:
            return {
                "variant_id": r["variant_id"],
                "sku": r["sku"],
                "product_title": r["product_title"],
                "variant_title": r["variant_title"],
                "available_quantity": r["available"],
                "units_sold": r["sold"],
            }

        by_sales = sorted(sold_rows, key=lambda r: r["sold"], reverse=True)
        return {
            "store_id": self.store_id,
            "window_days": days,
            "total_inventory_value": summary["inventory_value"],
            "total_available_units": summary["total_available_units"],
            "total_reserved_units": summary["total_reserved_units"],
            "out_of_stock_count": summary["out_of_stock_variants"],
            "fast_movers": [row(r) for r in by_sales if r["sold"] > 0][:limit],
            "dead_stock": [row(r) for r in by_sales if r["sold"] == 0 and r["available"] > 0][:limit],
            "dead_stock_count": sum(1 for r in sold_rows if r["sold"] == 0 and r["available"] > 0),
        }

    async def _sold_in_window(self, since: datetime) -> list[dict]:
        sold_sq = (
            select(OrderItem.variant_id.label("vid"), func.sum(OrderItem.quantity).label("sold"))
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.store_id == self.store_id, Order.ordered_at >= since)
            .group_by(OrderItem.variant_id)
            .subquery()
        )
        rows = (await self.db.execute(
            select(
                Variant.id, Variant.sku, Variant.title, Product.title,
                Variant.inventory_quantity, func.coalesce(sold_sq.c.sold, 0),
            )
            .select_from(Variant)
            .join(Product, Product.id == Variant.product_id)
            .outerjoin(sold_sq, sold_sq.c.vid == Variant.id)
            .where(Product.store_id == self.store_id)
        )).all()
        return [
            {
                "variant_id": vid, "sku": sku, "variant_title": vt, "product_title": pt,
                "available": qty or 0, "sold": int(sold or 0),
            }
            for vid, sku, vt, pt, qty, sold in rows
        ]
