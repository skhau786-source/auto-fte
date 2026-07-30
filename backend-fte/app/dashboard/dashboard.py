"""
Dashboard Router — exposes aggregate inventory monitoring data.

GET /dashboard — Returns complete inventory health summary
"""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent, Store

from app.inventory.dependencies import get_store_for_user
from app.dashboard.dashboard_service import DashboardService
from app.dashboard.dashboard_schema import DashboardResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "",
    response_model=DashboardResponse,
    summary="Get inventory dashboard",
    description="""
    Returns a comprehensive inventory monitoring dashboard for the
    authenticated user's store.

    Includes:
    - Inventory Summary (total products, variants, low stock, out of stock)
    - Today's Transactions (adjustments, syncs)
    - Sync Health (pending syncs, failed syncs)
    - Webhook Health (recent webhooks, errors)
    - Recent Errors (last 24 hours)
    """,
)
async def get_dashboard(
    store: Store = Depends(get_store_for_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the full inventory dashboard."""
    service = DashboardService(db=db, store=store)
    return await service.get_dashboard()
