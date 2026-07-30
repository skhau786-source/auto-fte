"""
Export Router — download inventory data in CSV, Excel, or JSON formats.

GET /export/products — Export products with variants
GET /export/transactions — Export inventory transactions
GET /export/logs — Export audit logs
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent, Store
from app.inventory.dependencies import get_store_for_user
from app.export.export_service import ExportService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/export", tags=["Data Export"])

VALID_FORMATS = {"csv", "json", "xlsx"}


@router.get(
    "/products",
    summary="Export products",
    description="""
    Download all products with optional variants in CSV, JSON, or Excel format.
    """,
)
async def export_products(
    format: str = Query("json", description="Export format: csv, json, xlsx"),
    include_variants: bool = Query(True, description="Include variant rows"),
    store: Store = Depends(get_store_for_user),
    db: AsyncSession = Depends(get_db),
):
    """Export products for the authenticated store."""
    if format not in VALID_FORMATS:
        return Response(
            content=f"Invalid format '{format}'. Valid options: csv, json, xlsx",
            status_code=400,
            media_type="text/plain",
        )

    service = ExportService(db)
    content_type, filename, data = await service.export_products(
        store_id=store.id,
        format=format,
        include_variants=include_variants,
    )

    return StreamingResponse(
        iter([data]),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/transactions",
    summary="Export inventory transactions",
    description="""
    Download inventory transaction history in CSV or JSON format.
    Supports optional date range filtering.
    """,
)
async def export_transactions(
    format: str = Query("json", description="Export format: csv, json"),
    date_from: Optional[str] = Query(None, description="Start date (ISO 8601)"),
    date_to: Optional[str] = Query(None, description="End date (ISO 8601)"),
    store: Store = Depends(get_store_for_user),
    db: AsyncSession = Depends(get_db),
):
    """Export inventory transactions."""
    if format not in {"csv", "json"}:
        return Response(
            content=f"Invalid format '{format}'. Valid options: csv, json",
            status_code=400,
            media_type="text/plain",
        )

    dt_from = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
    dt_to = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None

    service = ExportService(db)
    content_type, filename, data = await service.export_transactions(
        store_id=store.id,
        format=format,
        date_from=dt_from,
        date_to=dt_to,
    )

    return StreamingResponse(
        iter([data]),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/logs",
    summary="Export audit logs",
    description="""
    Download inventory audit logs in CSV or JSON format.
    """,
)
async def export_logs(
    format: str = Query("json", description="Export format: csv, json"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    date_from: Optional[str] = Query(None, description="Start date (ISO 8601)"),
    date_to: Optional[str] = Query(None, description="End date (ISO 8601)"),
    store: Store = Depends(get_store_for_user),
    db: AsyncSession = Depends(get_db),
):
    """Export audit logs for the store."""
    from app.inventory.audit_service import AuditService

    if format not in {"csv", "json"}:
        return Response(
            content=f"Invalid format '{format}'. Valid options: csv, json",
            status_code=400,
            media_type="text/plain",
        )

    dt_from = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
    dt_to = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None

    service = AuditService(db)
    content_type, data = await service.export_logs(
        store_id=store.id,
        format=format,
        date_from=dt_from,
        date_to=dt_to,
        action=action,
    )

    filename = f"audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"
    return StreamingResponse(
        iter([data]),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
