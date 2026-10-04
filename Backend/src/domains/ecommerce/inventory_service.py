# ═══════════════════════════════════════════════════════════════
# domains / ecommerce / inventory_service.py
#
# PURPOSE: Stock adjustments with an immutable ledger
#          (StockMovement). Low-stock alerts adjust ke baad
#          refresh hote hain (InventorySyncHandler ki logic reuse).
#
# USED BY: domains/ecommerce/inventory_routes.py
#
# NOTE:    Ported from kulsoom (backend-fte/app/inventory/service.py
#          adjust_inventory / bulk_adjust_inventory / get_history).
#          Platform write-back nahi hai — main ke connectors
#          read-only hain, isliye adjustment sirf local DB mein
#          hota hai (agla platform sync isay overwrite kar dega).
# ═══════════════════════════════════════════════════════════════

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.sdk.exceptions import AgentError
from src.sdk.models.base import Product, Variant
from src.sdk.models.inventory import StockMovement, MOVEMENT_ADJUSTMENT, MOVEMENT_TYPES
from src.domains.agents.inventory_sync.handler import InventorySyncHandler

logger = logging.getLogger(__name__)


class InsufficientStockError(AgentError):
    def __init__(self, variant_id: int, current: int, change: int):
        super().__init__(
            f"Insufficient stock for variant {variant_id}: have {current}, change {change}", code=409
        )


class VariantNotFoundError(AgentError):
    def __init__(self, variant_id: int):
        super().__init__(f"Variant {variant_id} not found in this store", code=404)


class InventoryService:
    """Stock operations scoped to one store."""

    def __init__(self, db: AsyncSession, store_id: int, user_id: Optional[int] = None):
        self.db = db
        self.store_id = store_id
        self.user_id = user_id

    async def _get_variant_locked(self, variant_id: int) -> Variant:
        """Variant fetch with row lock (lost-update se bachne ke liye), store-scoped."""
        result = await self.db.execute(
            select(Variant)
            .join(Product, Product.id == Variant.product_id)
            .where(Variant.id == variant_id, Product.store_id == self.store_id)
            .options(selectinload(Variant.product))
            .with_for_update(of=Variant)
        )
        variant = result.scalar_one_or_none()
        if variant is None:
            raise VariantNotFoundError(variant_id)
        return variant

    async def adjust_stock(
        self,
        variant_id: int,
        quantity_change: int,
        reason: Optional[str] = None,
        movement_type: str = MOVEMENT_ADJUSTMENT,
        reference_id: Optional[str] = None,
        commit: bool = True,
    ) -> dict:
        """Apply +/- quantity_change, record a ledger row, refresh low-stock alerts."""
        if quantity_change == 0:
            raise AgentError("quantity_change must not be 0", code=400)
        if movement_type not in MOVEMENT_TYPES:
            raise AgentError(f"Invalid movement_type '{movement_type}'", code=400)

        variant = await self._get_variant_locked(variant_id)

        before = variant.inventory_quantity or 0
        after = before + quantity_change
        if after < 0:
            raise InsufficientStockError(variant_id, before, quantity_change)

        variant.inventory_quantity = after
        movement = StockMovement(
            store_id=self.store_id,
            variant_id=variant_id,
            movement_type=movement_type,
            quantity_change=quantity_change,
            quantity_before=before,
            quantity_after=after,
            reason=reason,
            reference_id=reference_id,
            performed_by=self.user_id,
        )
        self.db.add(movement)
        await self.db.flush()

        await InventorySyncHandler(self.db)._check_and_alert_low_stock(variant)

        if commit:
            await self.db.commit()

        return {
            "variant_id": variant_id,
            "movement_id": movement.id,
            "quantity_before": before,
            "quantity_after": after,
            "quantity_change": quantity_change,
        }

    async def bulk_adjust(self, adjustments: list[dict]) -> list[dict]:
        """Many adjustments, ek commit. Expected errors per-item collect hote hain."""
        results: list[dict] = []
        for adj in adjustments:
            try:
                res = await self.adjust_stock(
                    variant_id=adj["variant_id"],
                    quantity_change=adj["quantity_change"],
                    reason=adj.get("reason"),
                    commit=False,
                )
                results.append({**res, "success": True})
            except AgentError as exc:
                results.append({"variant_id": adj["variant_id"], "success": False, "error": exc.message})
        await self.db.commit()
        return results

    async def get_history(
        self,
        variant_id: Optional[int] = None,
        movement_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StockMovement], int]:
        conditions = [StockMovement.store_id == self.store_id]
        if variant_id is not None:
            conditions.append(StockMovement.variant_id == variant_id)
        if movement_type:
            conditions.append(StockMovement.movement_type == movement_type)
        if date_from:
            conditions.append(StockMovement.created_at >= date_from)
        if date_to:
            conditions.append(StockMovement.created_at <= date_to)

        total = (await self.db.execute(
            select(func.count(StockMovement.id)).where(*conditions)
        )).scalar() or 0

        rows = (await self.db.execute(
            select(StockMovement)
            .where(*conditions)
            .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )).scalars().all()
        return list(rows), total
