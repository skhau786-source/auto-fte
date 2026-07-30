"""
Admin API Router — system administration endpoints for inventory management.

Requires a user with an active store. All operations are scoped to
the authenticated user's store.

Endpoints:
- POST /admin/sync/retry — Retry all failed syncs
- POST /admin/inventory/rebuild — Rebuild inventory from Shopify
- POST /admin/webhooks/re-register — Re-register all Shopify webhooks
- POST /admin/cache/flush — Flush Redis cache
- GET /admin/queue/status — View retry queue status
- GET /admin/queue/dead-letters — View dead letter queue
- GET /admin/stats — System statistics
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent, Store, InventoryTransaction, Product, ProductVariant

from app.inventory.dependencies import get_store_for_user
from app.inventory.service import InventoryService
from app.inventory.exceptions import ShopifySyncError
from app.inventory.repository import TransactionRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


async def _get_admin_service(
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store_for_user),
    user: RegisteredStudent = Depends(get_current_user),
) -> InventoryService:
    """Build InventoryService with store context."""
    return InventoryService(db=db, store=store, user_id=user.id)


# ═══════════════════════════════════════════════════════════════════
# POST /admin/sync/retry
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/sync/retry",
    summary="Retry all failed Shopify syncs",
    description="Attempts to push all unsynced transactions to Shopify again.",
)
async def retry_failed_syncs(
    service: InventoryService = Depends(_get_admin_service),
):
    """Retry all unsynced transactions for the store."""
    from app.inventory.shopify_client import ShopifyClient

    store = service.store
    txn_repo = TransactionRepository(service.db)

    unsynced = await txn_repo.get_unsynced(store.id, limit=100)
    if not unsynced:
        return {"message": "No unsynced transactions found", "retried": 0, "succeeded": 0, "failed": 0}

    from app.models import ProductVariant

    client = ShopifyClient(
        shop_domain=store.shopify_domain,
        access_token=store.access_token,
        location_id=store.shopify_location_id,
    )

    succeeded = 0
    failed = 0

    try:
        for txn in unsynced:
            try:
                variant_result = await service.db.execute(
                    select(ProductVariant).where(ProductVariant.id == txn.variant_id)
                )
                variant = variant_result.scalar_one_or_none()

                if not variant or not variant.shopify_inventory_item_id:
                    failed += 1
                    continue

                await client.set_inventory_level(
                    inventory_item_id=variant.shopify_inventory_item_id,
                    location_id=store.shopify_location_id,
                    quantity=txn.quantity_after,
                )

                await txn_repo.mark_synced(txn.id)
                succeeded += 1

            except Exception as exc:
                logger.warning("Retry failed for transaction %s: %s", txn.id, exc)
                failed += 1

        await service.db.commit()
    finally:
        await client.close()

    return {
        "message": f"Retry completed: {succeeded} succeeded, {failed} failed",
        "retried": len(unsynced),
        "succeeded": succeeded,
        "failed": failed,
    }


# ═══════════════════════════════════════════════════════════════════
# POST /admin/inventory/rebuild
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/inventory/rebuild",
    summary="Rebuild local inventory from Shopify",
    description="Force a full re-sync from Shopify, replacing all local products and variants.",
)
async def rebuild_inventory(
    service: InventoryService = Depends(_get_admin_service),
):
    """Force full re-sync from Shopify."""
    try:
        stats = await service.sync_from_shopify(force_full=True)
        return {"message": "Inventory rebuilt", "stats": stats}
    except ShopifySyncError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": str(exc), "error_code": "SHOPIFY_SYNC_ERROR"},
        )


# ═══════════════════════════════════════════════════════════════════
# POST /admin/webhooks/re-register
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/webhooks/re-register",
    summary="Re-register all Shopify webhooks",
    description="Registers all required webhooks for the current store.",
)
async def reregister_webhooks(
    service: InventoryService = Depends(_get_admin_service),
):
    """Re-register all Shopify webhooks for the store."""
    from app.inventory.webhook_registration import register_webhooks

    base_url = f"https://{service.store.shopify_domain}"
    results = await register_webhooks(
        shop_domain=service.store.shopify_domain,
        access_token=service.store.access_token,
        app_base_url=base_url,
    )

    return {"message": "Webhook registration completed", "results": results}


# ═══════════════════════════════════════════════════════════════════
# POST /admin/cache/flush
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/cache/flush",
    summary="Flush Redis cache",
    description="Clear all cached data for this store.",
)
async def flush_cache(
    service: InventoryService = Depends(_get_admin_service),
):
    """Flush the Redis cache for this store."""
    from app.cache.redis_cache import CacheService

    try:
        cache = CacheService()
        await cache.flush_pattern(f"store:{service.store.id}:*")
        await cache.close()
        return {"message": "Cache flushed successfully"}
    except Exception as exc:
        logger.warning("Cache flush failed (Redis may not be configured): %s", exc)
        return {"message": "Cache flush not available (Redis not configured)"}


# ═══════════════════════════════════════════════════════════════════
# GET /admin/queue/status
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/queue/status",
    summary="View retry queue status",
    description="View the current retry queue with pending syncs grouped by time.",
)
async def get_queue_status(
    service: InventoryService = Depends(_get_admin_service),
):
    """Get retry queue status — how many failed syncs need attention."""
    txn_repo = TransactionRepository(service.db)
    unsynced = await txn_repo.get_unsynced(service.store.id, limit=100)

    now = datetime.now(timezone.utc)
    age_buckets = {
        "recent_15m": 0,
        "recent_1h": 0,
        "recent_6h": 0,
        "older_6h": 0,
    }

    for txn in unsynced:
        age_hours = (now - txn.created_at).total_seconds() / 3600
        if age_hours <= 0.25:
            age_buckets["recent_15m"] += 1
        elif age_hours <= 1:
            age_buckets["recent_1h"] += 1
        elif age_hours <= 6:
            age_buckets["recent_6h"] += 1
        else:
            age_buckets["older_6h"] += 1

    return {
        "total_pending": len(unsynced),
        "age_distribution": age_buckets,
        "transactions": [
            {
                "id": str(t.id),
                "variant_id": str(t.variant_id),
                "quantity_change": t.quantity_change,
                "created_at": t.created_at.isoformat(),
                "age_hours": round((now - t.created_at).total_seconds() / 3600, 2),
            }
            for t in unsynced
        ],
    }


# ═══════════════════════════════════════════════════════════════════
# GET /admin/queue/dead-letters
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/queue/dead-letters",
    summary="View dead letter queue",
    description="View transactions that have failed all retry attempts and require manual intervention.",
)
async def get_dead_letters(
    service: InventoryService = Depends(_get_admin_service),
):
    """View dead letter transactions — those that can't be retried."""
    from app.inventory.retry_worker import DEAD_LETTER_THRESHOLD_HOURS, MAX_RETRY_ATTEMPTS

    txn_repo = TransactionRepository(service.db)
    unsynced = await txn_repo.get_unsynced(service.store.id, limit=200)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=DEAD_LETTER_THRESHOLD_HOURS)

    dead_letters = [
        {
            "id": str(t.id),
            "variant_id": str(t.variant_id),
            "quantity_change": t.quantity_change,
            "quantity_after": t.quantity_after,
            "created_at": t.created_at.isoformat(),
            "age_hours": round((now - t.created_at).total_seconds() / 3600, 1),
            "reason": t.reason,
        }
        for t in unsynced
        if t.created_at < cutoff
    ]

    return {
        "total_dead_letters": len(dead_letters),
        "max_retry_attempts": MAX_RETRY_ATTEMPTS,
        "dead_letter_threshold_hours": DEAD_LETTER_THRESHOLD_HOURS,
        "items": dead_letters,
    }


# ═══════════════════════════════════════════════════════════════════
# GET /admin/stats
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/stats",
    summary="System statistics",
    description="View system statistics for the store including total products, variants, transactions, sync health, and operation counts.",
)
async def get_system_stats(
    service: InventoryService = Depends(_get_admin_service),
):
    """Get comprehensive system statistics for the store."""
    from app.inventory.repository import ProductRepository

    stats = await ProductRepository(service.db).dashboard_stats(service.store.id)

    # Transaction counts by type
    type_counts_result = await service.db.execute(
        select(
            InventoryTransaction.transaction_type,
            func.count(InventoryTransaction.id),
        )
        .where(InventoryTransaction.variant_id.in_(
            select(ProductVariant.id).where(
                ProductVariant.product_id.in_(
                    select(Product.id).where(Product.store_id == service.store.id)
                )
            )
        ))
        .group_by(InventoryTransaction.transaction_type)
    )
    type_counts = {t: c for t, c in type_counts_result.all()}

    # Unsynced count
    txn_repo = TransactionRepository(service.db)
    unsynced = await txn_repo.get_unsynced(service.store.id, limit=1)

    return {
        "store": {
            "id": str(service.store.id),
            "domain": service.store.shopify_domain,
            "is_active": service.store.is_active,
            "has_location_id": service.store.shopify_location_id is not None,
        },
        "inventory": {
            "total_products": stats["total_products"],
            "total_variants": stats["total_variants"],
            "total_inventory_units": stats["total_inventory_units"],
            "total_value": str(stats.get("total_value", 0)),
            "low_stock_count": stats["low_stock_count"],
            "out_of_stock_count": stats["out_of_stock_count"],
        },
        "transactions": {
            "total": sum(type_counts.values()),
            "by_type": type_counts,
        },
        "sync": {
            "unsynced_count": len(unsynced),
            "has_pending_syncs": len(unsynced) > 0,
        },
    }

