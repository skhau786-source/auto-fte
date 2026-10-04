# ═══════════════════════════════════════════════════════════════
# domains / ecommerce / aggregation_routes.py
#
# PURPOSE: Inventory aggregation endpoints (read-only).
#
#   GET /api/v1/stores/{store_id}/inventory/summary
#   GET /api/v1/stores/{store_id}/inventory/products/{product_id}
#   GET /api/v1/stores/{store_id}/inventory/variants/{variant_id}
#   GET /api/v1/stores/{store_id}/inventory/report?days=30
#
#   product_id / variant_id = internal DB ids (jo /products response
#   mein "id" hote hain).
#
# NOTE:    Ported from kulsoom (backend-fte/app/inventory/aggregation_router.py).
# ═══════════════════════════════════════════════════════════════

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.sdk.database import get_db
from src.sdk.exceptions import AgentError
from src.domains.auth.models import User
from src.domains.auth.service import get_current_user
from src.domains.ecommerce.routes import _get_store_or_404
from src.domains.ecommerce.aggregation_service import AggregationService

router = APIRouter(prefix="/api/v1", tags=["Inventory"])


def _http_error(exc: AgentError) -> HTTPException:
    return HTTPException(status_code=exc.code if exc.code in (400, 404) else 400, detail=exc.message)


@router.get("/stores/{store_id}/inventory/summary")
async def inventory_summary(
    store_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_store_or_404(db, store_id, user.id)
    return await AggregationService(db, store_id).get_store_summary()


@router.get("/stores/{store_id}/inventory/products/{product_id}")
async def inventory_product(
    store_id: int,
    product_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_store_or_404(db, store_id, user.id)
    try:
        return await AggregationService(db, store_id).get_product(product_id)
    except AgentError as exc:
        raise _http_error(exc)


@router.get("/stores/{store_id}/inventory/variants/{variant_id}")
async def inventory_variant(
    store_id: int,
    variant_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_store_or_404(db, store_id, user.id)
    try:
        return await AggregationService(db, store_id).get_variant(variant_id)
    except AgentError as exc:
        raise _http_error(exc)


@router.get("/stores/{store_id}/inventory/report")
async def inventory_report(
    store_id: int,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_store_or_404(db, store_id, user.id)
    return await AggregationService(db, store_id).get_report(days=days, limit=limit)
