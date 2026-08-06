"""
API Router for the store-centric Inventory Aggregation Engine.

Endpoints:
  GET  /inventory/aggregate/store          — Store-level aggregation
  GET  /inventory/aggregate/product/{id}   — Product-level aggregation
  GET  /inventory/aggregate/variant/{id}   — Variant-level aggregation
  GET  /inventory/aggregate/dashboard      — Dashboard summary
  GET  /inventory/aggregate/reports        — Report data

Thin router layer — all business logic in InventoryAggregationEngine.
Ownership validation is built into every engine method.
"""

from __future__ import annotations

import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent, Store

from app.inventory.dependencies import get_store_for_user
from app.inventory.aggregation_engine import InventoryAggregationEngine
from app.inventory.exceptions import (
    ProductNotFoundError,
    VariantNotFoundError,
    InvalidStoreOwnershipError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/inventory/aggregate", tags=["Inventory Aggregation"])


# ═══════════════════════════════════════════════════════════════════
# Dependencies
# ═══════════════════════════════════════════════════════════════════

async def _get_agg_engine(
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store_for_user),
    user: RegisteredStudent = Depends(get_current_user),
) -> InventoryAggregationEngine:
    return InventoryAggregationEngine(db=db, store=store, user_id=user.id)


# ═══════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/store",
    summary="Get store-level inventory aggregation",
)
async def aggregate_store(
    engine: InventoryAggregationEngine = Depends(_get_agg_engine),
):
    """
    Aggregate inventory for the entire store.

    Returns total available/reserved inventory, inventory value,
    product/variant counts, low-stock and out-of-stock counts.
    """
    return await engine.get_store()


@router.get(
    "/product/{product_id}",
    summary="Get product-level inventory aggregation",
)
async def aggregate_product(
    product_id: uuid.UUID,
    engine: InventoryAggregationEngine = Depends(_get_agg_engine),
):
    """
    Aggregate inventory for an entire product (all variants).

    Returns total available/reserved/committed inventory, value,
    variant count, and a per-variant breakdown.
    """
    try:
        return await engine.get_product(product_id)
    except (ProductNotFoundError, InvalidStoreOwnershipError) as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
                if isinstance(exc, ProductNotFoundError)
                else status.HTTP_403_FORBIDDEN
            ),
            detail={
                "message": exc.message,
                "error_code": type(exc).__name__,
            },
        )


@router.get(
    "/variant/{variant_id}",
    summary="Get variant-level inventory aggregation",
)
async def aggregate_variant(
    variant_id: uuid.UUID,
    engine: InventoryAggregationEngine = Depends(_get_agg_engine),
):
    """
    Aggregate inventory for a single variant.

    Returns available/reserved/committed quantity, stock status,
    and inventory value.
    """
    try:
        return await engine.get_variant(variant_id)
    except (VariantNotFoundError, InvalidStoreOwnershipError) as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
                if isinstance(exc, VariantNotFoundError)
                else status.HTTP_403_FORBIDDEN
            ),
            detail={
                "message": exc.message,
                "error_code": type(exc).__name__,
            },
        )


@router.get(
    "/dashboard",
    summary="Get inventory aggregation dashboard summary",
)
async def aggregate_dashboard(
    engine: InventoryAggregationEngine = Depends(_get_agg_engine),
):
    """
    Dashboard summary — quick aggregation for frontend widgets.

    Returns total available/reserved inventory, inventory value,
    low-stock/out-of-stock counts, and active reservations.
    """
    return await engine.get_dashboard()


@router.get(
    "/reports",
    summary="Get inventory report data",
)
async def aggregate_reports(
    engine: InventoryAggregationEngine = Depends(_get_agg_engine),
):
    """
    Report aggregation data.

    Returns total inventory value, fast movers, slow movers,
    and dead stock count for the store.
    """
    return await engine.get_report_data()
