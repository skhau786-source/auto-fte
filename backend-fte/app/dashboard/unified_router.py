"""
Unified Dashboard Router — Phase 7.

GET /dashboard/unified — Returns a comprehensive dashboard combining
metrics from all 6 completed phases.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent, Store
from app.inventory.dependencies import get_store_for_user
from app.dashboard.unified_service import UnifiedDashboardService
from app.dashboard.unified_schema import UnifiedDashboardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Unified Dashboard"])


@router.get(
    "/unified",
    response_model=UnifiedDashboardResponse,
    summary="Get unified dashboard with all inventory metrics",
    description="""
    Returns a comprehensive dashboard combining metrics from all phases:

    Phase 1 — Inventory: Products, variants, stock levels, low stock
    Phase 2 — Reservation: Active reservations, success rate
    Phase 3 — Allocation: Strategy, allocated units, order coverage
    Phase 4 — Order Integration: Allocated/committed/released orders
    Phase 5 — Aggregation: Total available/reserved stock and value
    """,
)
async def get_unified_dashboard(
    store: Store = Depends(get_store_for_user),
    db: AsyncSession = Depends(get_db),
    user: RegisteredStudent = Depends(get_current_user),
) -> UnifiedDashboardResponse:
    """Get the full unified dashboard."""
    service = UnifiedDashboardService(
        db=db,
        store=store,
        user_id=user.id,
    )
    return await service.get_dashboard()
