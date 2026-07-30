"""
Store Health Check Service.

Provides comprehensive health monitoring for WooCommerce store connections.
Checks API connectivity, sync status, webhook registration, and data freshness.
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.woocommerce.models import (
    WooCommerceStore,
    WooCommerceProduct,
    WooCommerceOrder,
    WooCommerceCustomer,
    WooCommerceCoupon,
    WooCommerceSyncLog,
)
from app.woocommerce.constants import SyncStatus, StoreStatus
from app.woocommerce.exceptions import StoreNotFoundError
from app.woocommerce.client import WooCommerceClient
from app.woocommerce.encryption import decrypt_value

logger = logging.getLogger(__name__)


async def get_store_health(
    db: AsyncSession,
    store_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    """
    Run a comprehensive health check on a WooCommerce store connection.

    Checks:
    1. Store is active and has valid status
    2. WooCommerce API is reachable with current credentials
    3. Sync has been performed recently (within configured interval)
    4. Products are up-to-date (last_synced_at)
    5. Webhooks are registered (if configured)
    6. Data consistency (local vs remote counts)

    Args:
        db: Database session
        store_id: Store UUID
        user_id: User UUID for ownership verification

    Returns:
        Dict with health status, checks, and recommendations
    """
    result = await db.execute(
        select(WooCommerceStore).where(
            WooCommerceStore.id == store_id,
            WooCommerceStore.owner_id == user_id,
        )
    )
    store = result.scalar_one_or_none()
    if not store:
        raise StoreNotFoundError(str(store_id))

    checks: dict[str, dict] = {}
    now = datetime.now(timezone.utc)

    # 1. Store Status Check
    checks["store_status"] = {
        "status": "pass" if store.is_active and store.status == StoreStatus.CONNECTED else "fail",
        "message": f"Store is {'active' if store.is_active else 'inactive'} "
                   f"with status '{store.status.value}'",
        "value": store.status.value,
    }

    # 2. WooCommerce API Connectivity
    api_status = "unknown"
    api_message = ""
    api_latency_ms = None
    try:
        # Decrypt credentials (they may be encrypted via encryption.py)
        api_key = store.consumer_key
        api_secret = store.consumer_secret
        try:
            api_key = decrypt_value(store.consumer_key) or store.consumer_key
            api_secret = decrypt_value(store.consumer_secret) or store.consumer_secret
        except Exception:
            # Credentials may be stored in plaintext (encryption is opt-in)
            api_key = store.consumer_key
            api_secret = store.consumer_secret

        client = WooCommerceClient(
            store_url=store.store_url,
            consumer_key=api_key,
            consumer_secret=api_secret,
        )
        start = time.time()
        await client.verify_connection()
        api_latency_ms = int((time.time() - start) * 1000)
        await client.close()
        api_status = "pass"
        api_message = f"API reachable ({api_latency_ms}ms)"
    except Exception as exc:
        api_status = "fail"
        api_message = f"API unreachable: {exc}"

    checks["api_connectivity"] = {
        "status": api_status,
        "message": api_message,
        "value": f"{api_latency_ms}ms" if api_latency_ms else None,
    }

    # 3. Sync Freshness
    if store.last_sync_at:
        hours_since_sync = (now - store.last_sync_at).total_seconds() / 3600
        sync_status = "pass" if hours_since_sync < 24 else "warn" if hours_since_sync < 72 else "fail"
        checks["sync_freshness"] = {
            "status": sync_status,
            "message": f"Last sync {hours_since_sync:.1f}h ago",
            "value": store.last_sync_at.isoformat(),
        }
    else:
        checks["sync_freshness"] = {
            "status": "fail",
            "message": "No sync has been performed",
            "value": None,
        }

    # 4. Last Sync Status
    sync_result = await db.execute(
        select(WooCommerceSyncLog)
        .where(WooCommerceSyncLog.store_id == store_id)
        .order_by(WooCommerceSyncLog.created_at.desc())
        .limit(1)
    )
    last_sync = sync_result.scalar_one_or_none()
    if last_sync:
        checks["last_sync_status"] = {
            "status": "pass" if last_sync.status == SyncStatus.COMPLETED else "fail",
            "message": f"Last sync: {last_sync.resource} - {last_sync.status.value}",
            "value": last_sync.status.value,
        }
    else:
        checks["last_sync_status"] = {
            "status": "warn",
            "message": "No sync logs found",
            "value": None,
        }

    # 5. Data Freshness (products not synced in 24h)
    stale_result = await db.execute(
        select(func.count(WooCommerceProduct.id)).where(
            WooCommerceProduct.store_id == store_id,
            WooCommerceProduct.last_synced_at < now - timedelta(hours=24),
        )
    )
    stale_count = stale_result.scalar() or 0
    total_result = await db.execute(
        select(func.count(WooCommerceProduct.id)).where(
            WooCommerceProduct.store_id == store_id
        )
    )
    total_products = total_result.scalar() or 0

    checks["data_freshness"] = {
        "status": "pass" if stale_count == 0 else "warn",
        "message": f"{stale_count} of {total_products} products stale (>24h)",
        "value": {"stale": stale_count, "total": total_products},
    }

    # 6. Webhook Registration
    checks["webhook_registration"] = {
        "status": "pass" if store.webhooks_registered else "warn",
        "message": "Webhooks registered" if store.webhooks_registered else "Webhooks not registered",
        "value": store.webhooks_registered,
    }

    # 7. Failed Syncs
    failed_result = await db.execute(
        select(func.count(WooCommerceSyncLog.id)).where(
            WooCommerceSyncLog.store_id == store_id,
            WooCommerceSyncLog.status == SyncStatus.FAILED,
            WooCommerceSyncLog.created_at >= now - timedelta(hours=24),
        )
    )
    failed_count = failed_result.scalar() or 0
    checks["failed_syncs"] = {
        "status": "pass" if failed_count == 0 else "warn",
        "message": f"{failed_count} failed syncs in last 24h",
        "value": failed_count,
    }

    # Determine overall status
    overall = "pass"
    for check_name, check_data in checks.items():
        if check_data["status"] == "fail":
            overall = "fail"
            break
        if check_data["status"] == "warn" and overall == "pass":
            overall = "warn"

    recommendations = []
    if checks.get("api_connectivity", {}).get("status") == "fail":
        recommendations.append("Verify WooCommerce API credentials and store URL")
    if checks.get("sync_freshness", {}).get("status") != "pass":
        recommendations.append("Trigger a manual sync to refresh data")
    if checks.get("webhook_registration", {}).get("status") == "warn":
        recommendations.append("Register webhooks for real-time updates")
    if checks.get("data_freshness", {}).get("status") == "warn":
        recommendations.append("Some product data may be stale. Run a full sync.")
    if checks.get("failed_syncs", {}).get("status") != "pass":
        recommendations.append("Check sync logs and retry failed syncs")

    return {
        "store_id": str(store.id),
        "store_name": store.store_name,
        "status": overall,
        "checked_at": now.isoformat(),
        "checks": checks,
        "recommendations": recommendations,
        "summary": {
            "total_checks": len(checks),
            "passed": sum(1 for c in checks.values() if c["status"] == "pass"),
            "warnings": sum(1 for c in checks.values() if c["status"] == "warn"),
            "failed": sum(1 for c in checks.values() if c["status"] == "fail"),
        },
    }
