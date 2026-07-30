"""
Celery Background Tasks for the Warehouse Management module.

Periodic scheduled tasks for warehouse operations:
- Warehouse inventory sync with external platforms
- Warehouse health checks (connectivity, capacity)
- Capacity monitoring and alerts
- Transfer cleanup (stale transfers)
- Reservation cleanup (expired reservations)
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select, delete

from app.config import settings
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# ─── Celery App (shares the existing WooCommerce Celery app) ───
# Import the existing celery_app from tasks.py to share the same worker
from app.woocommerce.tasks import celery_app


# ─── Periodic Schedule Configuration ───

celery_app.conf.beat_schedule.update({
    "warehouse-health-check-daily": {
        "task": "app.warehouse.tasks.warehouse_health_check_all",
        "schedule": crontab(minute="0", hour="5"),  # Daily at 5 AM
    },
    "warehouse-capacity-monitoring-hourly": {
        "task": "app.warehouse.tasks.monitor_warehouse_capacity",
        "schedule": crontab(minute="30", hour="*"),  # Every hour at :30
    },
    "warehouse-transfer-cleanup-daily": {
        "task": "app.warehouse.tasks.cleanup_stale_transfers",
        "schedule": crontab(minute="0", hour="6"),  # Daily at 6 AM
    },
    "warehouse-reservation-cleanup-hourly": {
        "task": "app.warehouse.tasks.cleanup_expired_reservations",
        "schedule": crontab(minute="0", hour="*"),  # Every hour
    },
    "warehouse-inventory-sync-hourly": {
        "task": "app.warehouse.tasks.sync_warehouse_inventory_all",
        "schedule": crontab(minute="15", hour="*/2"),  # Every 2 hours
    },
})


# ═══════════════════════════════════════════════════════════════════
# TASK: Warehouse Health Check
# ═══════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.warehouse.tasks.warehouse_health_check_all", max_retries=3)
def warehouse_health_check_all(self):
    """Run health checks for all warehouses across all active stores."""
    logger.info("Starting warehouse health check for all stores")

    async def _run():
        async with AsyncSessionLocal() as db:
            from app.models import Store, Warehouse
            from app.inventory.constants import WarehouseStatus

            result = await db.execute(
                select(Store).where(Store.is_active == True)
            )
            stores = list(result.scalars().all())

            results = []
            for store in stores:
                wh_result = await db.execute(
                    select(Warehouse).where(
                        Warehouse.store_id == store.id,
                        Warehouse.is_active == True,
                    )
                )
                warehouses = list(wh_result.scalars().all())

                for wh in warehouses:
                    health = {
                        "warehouse_id": str(wh.id),
                        "warehouse_name": wh.name,
                        "status": wh.status.value,
                        "is_active": wh.is_active,
                        "has_capacity_limit": wh.capacity is not None,
                        "capacity": wh.capacity,
                    }

                    # Check if warehouse has recent activity
                    from app.models import WarehouseTransfer
                    recent_result = await db.execute(
                        select(WarehouseTransfer).where(
                            WarehouseTransfer.source_warehouse_id == wh.id,
                            WarehouseTransfer.created_at >= datetime.now(timezone.utc) - timedelta(days=7),
                        ).limit(1)
                    )
                    health["has_recent_activity"] = recent_result.first() is not None

                    results.append(health)

            return {"stores_checked": len(stores), "warehouses_checked": len(results), "results": results}

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
        logger.info("Warehouse health check completed: %s", result)
        return result
    except Exception as exc:
        logger.error("Warehouse health check failed: %s", exc)
        raise self.retry(exc=exc, countdown=300)
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════
# TASK: Capacity Monitoring
# ═══════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.warehouse.tasks.monitor_warehouse_capacity")
def monitor_warehouse_capacity(self):
    """Monitor warehouse capacity and log warnings for near-capacity warehouses."""
    logger.info("Starting warehouse capacity monitoring")

    async def _run():
        async with AsyncSessionLocal() as db:
            from app.models import Store, Warehouse, WarehouseInventory

            result = await db.execute(
                select(Store).where(Store.is_active == True)
            )
            stores = list(result.scalars().all())

            warnings = []
            for store in stores:
                wh_result = await db.execute(
                    select(Warehouse).where(
                        Warehouse.store_id == store.id,
                        Warehouse.is_active == True,
                        Warehouse.capacity.isnot(None),
                    )
                )
                warehouses = list(wh_result.scalars().all())

                for wh in warehouses:
                    if not wh.capacity:
                        continue

                    # Calculate current usage
                    inv_result = await db.execute(
                        select(
                            WarehouseInventory.available_stock,
                            WarehouseInventory.reserved_stock,
                            WarehouseInventory.incoming_stock,
                            WarehouseInventory.damaged_stock,
                        ).where(WarehouseInventory.warehouse_id == wh.id)
                    )
                    rows = inv_result.all()
                    total_used = sum(
                        (r.available_stock or 0) + (r.reserved_stock or 0) +
                        (r.incoming_stock or 0) + (r.damaged_stock or 0)
                        for r in rows
                    )

                    usage_pct = (total_used / wh.capacity) * 100 if wh.capacity > 0 else 0

                    if usage_pct >= 95:
                        level = "CRITICAL"
                    elif usage_pct >= 80:
                        level = "WARNING"
                    else:
                        continue

                    warnings.append({
                        "warehouse_id": str(wh.id),
                        "warehouse_name": wh.name,
                        "capacity": wh.capacity,
                        "current_usage": total_used,
                        "usage_percentage": round(usage_pct, 1),
                        "level": level,
                    })
                    logger.warning(
                        "Capacity %s: %s at %.1f%% (%d/%d)",
                        level, wh.name, usage_pct, total_used, wh.capacity,
                    )

            return {"warehouses_checked": len([w for s in stores for w in []]), "warnings": warnings}

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
        logger.info("Capacity monitoring completed: %d warnings", len(result.get("warnings", [])))
        return result
    except Exception as exc:
        logger.error("Capacity monitoring failed: %s", exc)
        return {"error": str(exc)}
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════
# TASK: Transfer Cleanup
# ═══════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.warehouse.tasks.cleanup_stale_transfers")
def cleanup_stale_transfers(self):
    """Cancel transfers that have been stuck in draft/pending for too long."""
    logger.info("Starting stale transfer cleanup")

    async def _run():
        async with AsyncSessionLocal() as db:
            from app.models import WarehouseTransfer
            from app.inventory.constants import TransferStatus

            cutoff = datetime.now(timezone.utc) - timedelta(days=7)

            # Find stale draft transfers (older than 7 days)
            stale_result = await db.execute(
                select(WarehouseTransfer).where(
                    WarehouseTransfer.status.in_([TransferStatus.DRAFT, TransferStatus.PENDING]),
                    WarehouseTransfer.created_at < cutoff,
                )
            )
            stale_transfers = list(stale_result.scalars().all())

            cancelled = 0
            for transfer in stale_transfers:
                transfer.status = TransferStatus.CANCELLED
                cancelled += 1
                logger.info(
                    "Cancelled stale transfer %s (created %s, status %s)",
                    transfer.transfer_number, transfer.created_at, transfer.status,
                )

            # Also clean up stuck IN_TRANSIT transfers older than 30 days
            in_transit_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            stuck_result = await db.execute(
                select(WarehouseTransfer).where(
                    WarehouseTransfer.status == TransferStatus.IN_TRANSIT,
                    WarehouseTransfer.created_at < in_transit_cutoff,
                )
            )
            stuck_transfers = list(stuck_result.scalars().all())

            for transfer in stuck_transfers:
                transfer.status = TransferStatus.CANCELLED
                cancelled += 1
                logger.info(
                    "Cancelled stuck in-transit transfer %s (created %s)",
                    transfer.transfer_number, transfer.created_at,
                )

            await db.commit()
            return {"cancelled": cancelled, "total_stale": len(stale_transfers), "total_stuck": len(stuck_transfers)}

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
        logger.info("Stale transfer cleanup completed: %s", result)
        return result
    except Exception as exc:
        logger.error("Stale transfer cleanup failed: %s", exc)
        return {"error": str(exc)}
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════
# TASK: Reservation Cleanup
# ═══════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.warehouse.tasks.cleanup_expired_reservations")
def cleanup_expired_reservations(self):
    """Release expired stock reservations."""
    logger.info("Starting expired reservation cleanup")

    async def _run():
        async with AsyncSessionLocal() as db:
            from app.models import Warehouse, WarehouseInventory

            now = datetime.now(timezone.utc)

            # Find warehouses with inventory that might have stale reservations
            # For now, we don't have an explicit reservation model, so this
            # logs the intent — reservations are stored in reserved_stock field
            # and released manually through the release_reservation service method.
            #
            # A future enhancement could add a Reservation model with expiry dates.

            logger.info("Expired reservation cleanup: no explicit reservation model yet")
            return {"status": "noop", "message": "Reservation cleanup requires explicit Reservation model"}

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
        logger.info("Reservation cleanup completed: %s", result)
        return result
    except Exception as exc:
        logger.error("Reservation cleanup failed: %s", exc)
        return {"error": str(exc)}
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════
# TASK: Sync Warehouse Inventory (placeholder)
# ═══════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.warehouse.tasks.sync_warehouse_inventory_all")
def sync_warehouse_inventory_all(self):
    """Sync warehouse inventory levels to external platforms (Shopify, WooCommerce)."""
    logger.info("Starting warehouse inventory sync")

    async def _run():
        async with AsyncSessionLocal() as db:
            from app.models import Store, Warehouse, WarehouseInventory, ProductVariant

            result = await db.execute(
                select(Store).where(Store.is_active == True)
            )
            stores = list(result.scalars().all())

            total_variants_synced = 0

            for store in stores:
                if not store.shopify_domain or not store.access_token:
                    continue

                # This would call the external API to sync inventory levels
                # For now, it's a placeholder that logs the intent
                logger.info(
                    "Would sync warehouse inventory for store %s",
                    store.shopify_domain,
                )

            return {"stores_processed": len(stores), "variants_synced": total_variants_synced}

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
        logger.info("Warehouse inventory sync completed: %s", result)
        return result
    except Exception as exc:
        logger.error("Warehouse inventory sync failed: %s", exc)
        return {"error": str(exc)}
    finally:
        loop.close()
