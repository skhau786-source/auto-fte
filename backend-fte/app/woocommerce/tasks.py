"""
Celery Background Tasks for the WooCommerce Integration Module.

Defines all asynchronous task definitions for data synchronization.
Uses Celery for distributed task execution with Redis as the message broker.

Tasks:
- run_initial_sync: Full initial sync when a store is first connected
- sync_products_task: Scheduled product sync
- sync_orders_task: Scheduled order sync
- sync_customers_task: Scheduled customer sync
- sync_categories_task: Scheduled category sync
- sync_coupons_task: Scheduled coupon sync
- sync_all_task: Complete sync of all resources
- retry_failed_syncs: Retry failed sync operations
- check_low_stock: Periodic low stock check
- cleanup_old_data: Data retention cleanup
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from celery import Celery
from celery.schedules import crontab
from celery.signals import after_setup_logger
from sqlalchemy import select, delete

from app.config import settings
from app.database import AsyncSessionLocal
from app.woocommerce.service import WooCommerceService

logger = logging.getLogger(__name__)

# ─── Celery App Initialization ───

celery_app = Celery(
    "digital_fte_woocommerce",
    broker=settings.CELERY_BROKER_URL or "redis://localhost:6379/0",
    backend=settings.CELERY_RESULT_BACKEND or "redis://localhost:6379/0",
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=3600,  # 1 hour soft limit
    task_time_limit=7200,  # 2 hour hard limit
)

# ─── Periodic Schedule Configuration ───

celery_app.conf.beat_schedule = {
    "sync-inventory-every-5-minutes": {
        "task": "app.woocommerce.tasks.sync_inventory_all_stores",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
    "sync-orders-every-10-minutes": {
        "task": "app.woocommerce.tasks.sync_all_active_stores",
        "schedule": crontab(minute="*/10"),  # Every 10 minutes
        "kwargs": {"resources": ["orders"]},
    },
    "sync-customers-every-30-minutes": {
        "task": "app.woocommerce.tasks.sync_all_active_stores",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
        "kwargs": {"resources": ["customers"]},
    },
    "sync-categories-every-1-hour": {
        "task": "app.woocommerce.tasks.sync_all_active_stores",
        "schedule": crontab(minute="0", hour="*"),  # Every hour
        "kwargs": {"resources": ["categories"]},
    },
    "sync-coupons-every-1-hour": {
        "task": "app.woocommerce.tasks.sync_all_active_stores",
        "schedule": crontab(minute="15", hour="*"),  # Every hour at :15
        "kwargs": {"resources": ["coupons"]},
    },
    "sync-products-every-6-hours": {
        "task": "app.woocommerce.tasks.sync_all_active_stores",
        "schedule": crontab(minute="0", hour="*/6"),  # Every 6 hours
        "kwargs": {"resources": ["products", "categories"]},
    },
    "full-sync-daily": {
        "task": "app.woocommerce.tasks.full_sync_all_active_stores",
        "schedule": crontab(minute="0", hour="2"),  # Daily at 2 AM
    },
    "check-low-stock-every-hour": {
        "task": "app.woocommerce.tasks.check_low_stock_all_stores",
        "schedule": crontab(minute="45", hour="*"),  # Every hour at :45
    },
    "process-webhook-queue-every-minute": {
        "task": "app.woocommerce.tasks.process_webhook_queue",
        "schedule": crontab(minute="*/1"),  # Every minute
    },
    "health-check-daily": {
        "task": "app.woocommerce.tasks.run_health_check_all_stores",
        "schedule": crontab(minute="0", hour="4"),  # Daily at 4 AM
    },
    "cleanup-old-data-weekly": {
        "task": "app.woocommerce.tasks.cleanup_old_data",
        "schedule": crontab(minute="0", hour="3", day_of_week="0"),  # Weekly on Sunday at 3 AM
    },
    "retry-failed-syncs-every-15-minutes": {
        "task": "app.woocommerce.tasks.retry_failed_syncs",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
    },
    "cleanup-failed-jobs-daily": {
        "task": "app.woocommerce.tasks.cleanup_failed_jobs",
        "schedule": crontab(minute="0", hour="5"),  # Daily at 5 AM
    },
}


# ═══════════════════════════════════════════════════════════════════
# TASK: Initial Sync (called after store connection)
# ═══════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.woocommerce.tasks.run_initial_sync", max_retries=3)
def run_initial_sync(self, store_id: str, user_id: str):
    """Run initial full synchronization for a newly connected store."""
    logger.info("Starting initial sync for store %s", store_id)

    async def _run():
        async with AsyncSessionLocal() as db:
            from app.woocommerce.models import WooCommerceStore
            from app.models import RegisteredStudent

            result = await db.execute(
                select(RegisteredStudent).where(RegisteredStudent.id == user_id)
            )
            user = result.scalar_one_or_none()
            service = WooCommerceService(db=db, user=user)

            resources = ["categories", "products", "orders", "customers", "coupons"]
            results = {}

            for resource in resources:
                try:
                    if resource == "categories":
                        results[resource] = await service.sync_categories(store_id)
                    elif resource == "products":
                        results[resource] = await service.sync_products(store_id, force_full=True)
                    elif resource == "orders":
                        results[resource] = await service.sync_orders(store_id)
                    elif resource == "customers":
                        results[resource] = await service.sync_customers(store_id)
                    elif resource == "coupons":
                        results[resource] = await service.sync_coupons(store_id)
                    logger.info("Initial sync %s for store %s: %s", resource, store_id, results.get(resource))
                except Exception as exc:
                    logger.error("Initial sync %s failed for store %s: %s", resource, store_id, exc)
                    results[resource] = {"error": str(exc)}

            return results

    loop = asyncio.new_event_loop()
    try:
        results = loop.run_until_complete(_run())
        logger.info("Initial sync completed for store %s: %s", store_id, results)
        return results
    except Exception as exc:
        logger.error("Initial sync failed for store %s: %s", store_id, exc)
        raise self.retry(exc=exc, countdown=300)  # Retry in 5 minutes
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════
# TASK: Sync All Active Stores
# ═══════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.woocommerce.tasks.sync_all_active_stores", max_retries=3)
def sync_all_active_stores(self, resources: list[str] = None):
    """Sync specified resources for all active stores."""
    logger.info("Starting sync for all active stores: %s", resources)

    async def _run():
        async with AsyncSessionLocal() as db:
            from app.woocommerce.models import WooCommerceStore
            from app.woocommerce.constants import StoreStatus

            result = await db.execute(
                select(WooCommerceStore).where(
                    WooCommerceStore.is_active == True,
                    WooCommerceStore.status == StoreStatus.CONNECTED,
                )
            )
            stores = list(result.scalars().all())

            results = {}
            for store in stores:
                service = WooCommerceService(db=db, user=None)
                store_results = {}
                for resource in (resources or ["products"]):
                    try:
                        if resource == "products":
                            store_results[resource] = await service.sync_products(str(store.id))
                        elif resource == "orders":
                            store_results[resource] = await service.sync_orders(str(store.id))
                        elif resource == "customers":
                            store_results[resource] = await service.sync_customers(str(store.id))
                        elif resource == "categories":
                            store_results[resource] = await service.sync_categories(str(store.id))
                        elif resource == "coupons":
                            store_results[resource] = await service.sync_coupons(str(store.id))
                    except Exception as exc:
                        logger.error("Sync %s failed for store %s: %s", resource, store.store_name, exc)
                        store_results[resource] = {"error": str(exc)}

                results[str(store.id)] = store_results

            return results

    loop = asyncio.new_event_loop()
    try:
        results = loop.run_until_complete(_run())
        logger.info("Sync completed for all active stores")
        return results
    except Exception as exc:
        logger.error("Sync all active stores failed: %s", exc)
        raise self.retry(exc=exc, countdown=300)
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════
# TASK: Full Sync All Active Stores
# ═══════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.woocommerce.tasks.full_sync_all_active_stores", max_retries=3)
def full_sync_all_active_stores(self):
    """Full sync (with force_full) for all active stores."""
    return sync_all_active_stores(resources=["products", "orders", "customers", "categories", "coupons"])


# ═══════════════════════════════════════════════════════════════════
# TASK: Check Low Stock
# ═══════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.woocommerce.tasks.check_low_stock_all_stores")
def check_low_stock_all_stores(self):
    """Check low stock levels for all active stores and create alerts."""
    from app.woocommerce.models import (
        WooCommerceStore, WooCommerceSetting,
        WooCommerceProduct, WooCommerceAlert,
    )
    from app.woocommerce.constants import AlertType, AlertSeverity

    logger.info("Starting low stock check for all active stores")

    async def _run():
        async with AsyncSessionLocal() as db:
            from app.woocommerce.constants import AlertType, AlertSeverity

            result = await db.execute(
                select(WooCommerceStore).where(WooCommerceStore.is_active == True)
            )
            stores = list(result.scalars().all())

            alerts_created = 0
            for store in stores:
                # Get store settings
                settings_result = await db.execute(
                    select(WooCommerceSetting).where(WooCommerceSetting.store_id == store.id)
                )
                settings = settings_result.scalar_one_or_none()
                if not settings or not settings.low_stock_alerts:
                    continue

                threshold = settings.low_stock_threshold or 10

                # Find low stock products
                products_result = await db.execute(
                    select(WooCommerceProduct).where(
                        WooCommerceProduct.store_id == store.id,
                        WooCommerceProduct.manage_stock == True,
                        WooCommerceProduct.stock_quantity <= threshold,
                        WooCommerceProduct.stock_quantity > 0,
                    )
                )
                low_stock_products = list(products_result.scalars().all())

                for product in low_stock_products:
                    # Check if alert already exists (unresolved)
                    existing = await db.execute(
                        select(WooCommerceAlert).where(
                            WooCommerceAlert.store_id == store.id,
                            WooCommerceAlert.alert_type == AlertType.LOW_STOCK,
                            WooCommerceAlert.resource_id == str(product.wc_product_id),
                            WooCommerceAlert.is_resolved == False,
                        )
                    )
                    if not existing.scalar_one_or_none():
                        alert = WooCommerceAlert(
                            store_id=store.id,
                            alert_type=AlertType.LOW_STOCK,
                            severity=AlertSeverity.WARNING,
                            title=f"Low Stock: {product.name}",
                            message=f"Product '{product.name}' (SKU: {product.sku}) has only {product.stock_quantity} units remaining.",
                            resource_type="product",
                            resource_id=str(product.wc_product_id),
                        )
                        db.add(alert)
                        alerts_created += 1

            await db.commit()
            return {"alerts_created": alerts_created}

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
        logger.info("Low stock check completed: %s", result)
        return result
    except Exception as exc:
        logger.error("Low stock check failed: %s", exc)
        return {"error": str(exc)}
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════
# TASK: Retry Failed Syncs
# ═══════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.woocommerce.tasks.retry_failed_syncs")
def retry_failed_syncs(self):
    """Retry all failed sync operations for all active stores."""
    logger.info("Starting retry of failed syncs")

    async def _run():
        async with AsyncSessionLocal() as db:
            from app.woocommerce.models import WooCommerceStore, WooCommerceSyncLog
            from app.woocommerce.constants import SyncStatus

            # Find failed syncs within the last 24 hours
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            result = await db.execute(
                select(WooCommerceSyncLog).where(
                    WooCommerceSyncLog.status == SyncStatus.FAILED,
                    WooCommerceSyncLog.created_at >= cutoff,
                ).order_by(WooCommerceSyncLog.created_at.desc()).limit(50)
            )
            failed_syncs = list(result.scalars().all())

            retried = 0
            for sync_log in failed_syncs:
                try:
                    # Get store
                    store_result = await db.execute(
                        select(WooCommerceStore).where(
                            WooCommerceStore.id == sync_log.store_id,
                            WooCommerceStore.is_active == True,
                        )
                    )
                    store = store_result.scalar_one_or_none()
                    if not store:
                        continue

                    service = WooCommerceService(db=db, user=None)
                    resource = sync_log.resource

                    if resource == "products":
                        await service.sync_products(str(store.id))
                    elif resource == "orders":
                        await service.sync_orders(str(store.id))
                    elif resource == "customers":
                        await service.sync_customers(str(store.id))
                    elif resource == "categories":
                        await service.sync_categories(str(store.id))
                    elif resource == "coupons":
                        await service.sync_coupons(str(store.id))

                    retried += 1

                except Exception as exc:
                    logger.warning("Retry failed for sync %s: %s", sync_log.id, exc)

            return {"retried": retried, "total_failed": len(failed_syncs)}

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
        logger.info("Retry failed syncs completed: %s", result)
        return result
    except Exception as exc:
        logger.error("Retry failed syncs error: %s", exc)
        return {"error": str(exc)}
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════
# TASK: Cleanup Old Data
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# TASK: Process Webhook Queue
# ═══════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.woocommerce.tasks.process_webhook_queue", max_retries=3)
def process_webhook_queue(self):
    """Process pending webhooks from the webhook queue."""
    logger.info("Processing webhook queue")
    from app.woocommerce.webhook_queue import WebhookQueue

    async def _run():
        queue = WebhookQueue()
        processed = 0

        # Process up to 10 webhooks per run
        # Process main queue
        for _ in range(10):
            webhook = await queue.dequeue()
            if not webhook:
                break
            processed += 1

        # Process retry queue (retries with exponential backoff)
        for _ in range(5):
            webhook = await queue.dequeue_retry()
            if not webhook:
                break
            processed += 1

        return {"processed": processed}

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
        logger.info("Webhook queue processed: %s", result)
        return result
    except Exception as exc:
        logger.error("Webhook queue processing failed: %s", exc)
        return {"error": str(exc)}
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════
# TASK: Sync Inventory All Stores
# ═══════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.woocommerce.tasks.sync_inventory_all_stores", max_retries=3)
def sync_inventory_all_stores(self):
    """Sync inventory for all active stores."""
    logger.info("Starting inventory sync for all active stores")

    async def _run():
        async with AsyncSessionLocal() as db:
            from app.woocommerce.models import WooCommerceStore
            from app.woocommerce.constants import StoreStatus

            result = await db.execute(
                select(WooCommerceStore).where(
                    WooCommerceStore.is_active == True,
                    WooCommerceStore.status == StoreStatus.CONNECTED,
                )
            )
            stores = list(result.scalars().all())

            updated = 0
            for store in stores:
                try:
                    service = WooCommerceService(db=db, user=None)
                    # Re-sync products to update stock quantities
                    sync_result = await service.sync_products(str(store.id))
                    updated += sync_result.get("updated", 0) + sync_result.get("created", 0)
                except Exception as exc:
                    logger.error(
                        "Inventory sync failed for store %s: %s",
                        store.store_name, exc,
                    )

            return {"stores_processed": len(stores), "items_updated": updated}

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
        logger.info("Inventory sync completed: %s", result)
        return result
    except Exception as exc:
        logger.error("Inventory sync all stores failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════
# TASK: Health Check All Stores
# ═══════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.woocommerce.tasks.run_health_check_all_stores")
def run_health_check_all_stores(self):
    """Run health checks for all active stores."""
    logger.info("Starting health checks for all active stores")

    async def _run():
        async with AsyncSessionLocal() as db:
            from app.woocommerce.models import WooCommerceStore
            from app.woocommerce.health import get_store_health

            result = await db.execute(
                select(WooCommerceStore).where(WooCommerceStore.is_active == True)
            )
            stores = list(result.scalars().all())

            results = []
            for store in stores:
                try:
                    health = await get_store_health(
                        db=db, store_id=store.id, user_id=store.owner_id,
                    )
                    results.append({
                        "store_id": str(store.id),
                        "store_name": store.store_name,
                        "status": health.get("status"),
                    })
                except Exception as exc:
                    logger.error(
                        "Health check failed for store %s: %s",
                        store.store_name, exc,
                    )

            return {"stores_checked": len(results), "results": results}

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
        logger.info("Health checks completed: %s", result)
        return result
    except Exception as exc:
        logger.error("Health check all stores failed: %s", exc)
        return {"error": str(exc)}
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════
# TASK: Cleanup Failed Jobs
# ═══════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.woocommerce.tasks.cleanup_failed_jobs")
def cleanup_failed_jobs(self):
    """Clean up stale failed jobs older than the dead letter threshold."""
    logger.info("Starting failed jobs cleanup")

    async def _run():
        async with AsyncSessionLocal() as db:
            from app.woocommerce.models import WooCommerceSyncLog
            from app.woocommerce.constants import SyncStatus, DEAD_LETTER_THRESHOLD_HOURS

            cutoff = datetime.now(timezone.utc) - timedelta(hours=DEAD_LETTER_THRESHOLD_HOURS)

            # Clean old failed sync logs
            result = await db.execute(
                delete(WooCommerceSyncLog).where(
                    WooCommerceSyncLog.status == SyncStatus.FAILED,
                    WooCommerceSyncLog.created_at < cutoff,
                )
            )
            deleted = result.rowcount
            await db.commit()

            return {"deleted_failed_sync_logs": deleted}

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
        logger.info("Failed jobs cleanup completed: %s", result)
        return result
    except Exception as exc:
        logger.error("Failed jobs cleanup failed: %s", exc)
        return {"error": str(exc)}
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════
# TASK: Cleanup Old Data
# ═══════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.woocommerce.tasks.cleanup_old_data")
def cleanup_old_data(self):
    """
    Clean up old data based on store retention settings.
    Removes inventory logs, sync logs, and alerts older than the retention period.
    """
    logger.info("Starting data cleanup")

    async def _run():
        async with AsyncSessionLocal() as db:
            from app.woocommerce.models import WooCommerceStore, WooCommerceSetting, WooCommerceInventoryLog, WooCommerceSyncLog, WooCommerceAlert

            result = await db.execute(
                select(WooCommerceStore).where(WooCommerceStore.is_active == True)
            )
            stores = list(result.scalars().all())

            total_deleted = {"logs": 0, "sync_logs": 0, "alerts": 0}

            for store in stores:
                settings_result = await db.execute(
                    select(WooCommerceSetting).where(WooCommerceSetting.store_id == store.id)
                )
                settings = settings_result.scalar_one_or_none()
                if not settings or not settings.archive_old_data:
                    continue

                retention_days = settings.retention_days or 90
                cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

                # Delete old inventory logs
                delete_logs = await db.execute(
                    delete(WooCommerceInventoryLog).where(
                        WooCommerceInventoryLog.store_id == store.id,
                        WooCommerceInventoryLog.created_at < cutoff,
                    )
                )
                total_deleted["logs"] += delete_logs.rowcount

                # Delete old sync logs
                delete_syncs = await db.execute(
                    delete(WooCommerceSyncLog).where(
                        WooCommerceSyncLog.store_id == store.id,
                        WooCommerceSyncLog.created_at < cutoff,
                    )
                )
                total_deleted["sync_logs"] += delete_syncs.rowcount

                # Delete old resolved alerts
                delete_alerts = await db.execute(
                    delete(WooCommerceAlert).where(
                        WooCommerceAlert.store_id == store.id,
                        WooCommerceAlert.is_resolved == True,
                        WooCommerceAlert.created_at < cutoff,
                    )
                )
                total_deleted["alerts"] += delete_alerts.rowcount

            await db.commit()
            return total_deleted

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
        logger.info("Data cleanup completed: %s", result)
        return result
    except Exception as exc:
        logger.error("Data cleanup failed: %s", exc)
        return {"error": str(exc)}
    finally:
        loop.close()
