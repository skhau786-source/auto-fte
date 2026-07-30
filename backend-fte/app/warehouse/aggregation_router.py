"""
API Router for Inventory Aggregation Engine — Phase 6 (F.7).

Endpoints:
  GET  /inventory/aggregate/store          — Store-level aggregation (F.5)
  GET  /inventory/aggregate/warehouse/{id}  — Warehouse-level aggregation (F.4)
  GET  /inventory/aggregate/product/{id}    — Product-level aggregation (F.3)
  GET  /inventory/aggregate/variant/{id}    — Variant-level aggregation (F.2)
  GET  /inventory/aggregate/dashboard       — Dashboard summary (F.6)
  GET  /inventory/aggregate/distribution/{variant_id} — Distribution (F.7)
  GET  /inventory/aggregate/reports         — Report data (F.11)

Thin router layer — all business logic in InventoryAggregationEngine.
Ownership validation is built into every engine method.
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent, Store

from app.inventory.dependencies import get_store_for_user
from app.warehouse.aggregation_engine import InventoryAggregationEngine
from app.warehouse.exceptions import WarehouseNotFoundError
from app.inventory.exceptions import InvalidStoreOwnershipError

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
    Aggregate inventory for the entire store (F.5).

    Returns total available, reserved, incoming, damaged stock,
    inventory value, warehouse/product/variant counts, and more.
    """
    return await engine.get_store()


@router.get(
    "/warehouse/{warehouse_id}",
    summary="Get warehouse-level inventory aggregation",
)
async def aggregate_warehouse(
    warehouse_id: uuid.UUID,
    engine: InventoryAggregationEngine = Depends(_get_agg_engine),
):
    """
    Aggregate inventory for a specific warehouse (F.4).

    Returns available/reserved/incoming/damaged stock, capacity,
    SKU/variant/product counts, and reservation counts.
    """
    try:
        return await engine.get_warehouse(warehouse_id)
    except WarehouseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        )


@router.get(
    "/product/{product_id}",
    summary="Get product-level inventory aggregation",
)
async def aggregate_product(
    product_id: uuid.UUID,
    engine: InventoryAggregationEngine = Depends(_get_agg_engine),
):
    """
    Aggregate inventory for an entire product (all variants, all warehouses) (F.3).

    Returns total available/reserved/incoming/damaged across all variants,
    variant count, warehouse count, and per-variant breakdown.
    """
    return await engine.get_product(product_id)


@router.get(
    "/variant/{variant_id}",
    summary="Get variant-level inventory aggregation",
)
async def aggregate_variant(
    variant_id: uuid.UUID,
    engine: InventoryAggregationEngine = Depends(_get_agg_engine),
):
    """
    Aggregate inventory for a single variant across all warehouses (F.2).

    Returns total/available/reserved/incoming/damaged/allocated/in_transit stock,
    warehouse count, and per-warehouse breakdown.
    """
    return await engine.get_variant(variant_id)


@router.get(
    "/dashboard",
    summary="Get inventory aggregation dashboard summary",
)
async def aggregate_dashboard(
    engine: InventoryAggregationEngine = Depends(_get_agg_engine),
):
    """
    Dashboard summary (F.6) — quick aggregation for frontend widgets.

    Returns total available/reserved/incoming/damaged inventory,
    inventory value, warehouse/active warehouse counts,
    active reservations, and transfer in transit count.
    """
    return await engine.get_dashboard()


@router.get(
    "/distribution/{variant_id}",
    summary="Get stock distribution for a variant across warehouses",
)
async def aggregate_distribution(
    variant_id: uuid.UUID,
    engine: InventoryAggregationEngine = Depends(_get_agg_engine),
):
    """
    Get stock distribution (F.7) — per-warehouse breakdown with percentages.

    Shows how a variant's stock is distributed across all warehouses.
    """
    return await engine.get_distribution(variant_id)


@router.get(
    "/reports",
    summary="Get inventory report data",
)
async def aggregate_reports(
    engine: InventoryAggregationEngine = Depends(_get_agg_engine),
):
    """
    Report aggregation data (F.11).

    Returns inventory value by warehouse, warehouse utilization,
    fast movers, slow movers, and dead stock count.
    """
    return await engine.get_report_data()
