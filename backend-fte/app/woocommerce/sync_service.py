"""
Sync Log service additions for WooCommerceService.

This file adds the get_sync_logs method to WooCommerceService.
It's imported by the router to maintain clean architecture.
"""

from typing import Optional
from datetime import datetime
import uuid

from sqlalchemy import select, func

from app.woocommerce.models import WooCommerceSyncLog


async def get_sync_logs(
    service,
    store_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
    resource: Optional[str] = None,
    status: Optional[str] = None,
) -> tuple[list[WooCommerceSyncLog], int]:
    """Get paginated sync logs for a store."""
    query = select(WooCommerceSyncLog).where(WooCommerceSyncLog.store_id == store_id)
    count_query = select(func.count(WooCommerceSyncLog.id)).where(WooCommerceSyncLog.store_id == store_id)

    if resource:
        query = query.where(WooCommerceSyncLog.resource == resource)
        count_query = count_query.where(WooCommerceSyncLog.resource == resource)

    if status:
        query = query.where(WooCommerceSyncLog.status == status)
        count_query = count_query.where(WooCommerceSyncLog.status == status)

    total_result = await service.db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(WooCommerceSyncLog.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await service.db.execute(query)
    logs = list(result.scalars().all())

    return logs, total
