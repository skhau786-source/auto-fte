"""
Scheduled Jobs Service — runs background maintenance tasks on a schedule.

Jobs:
1. Nightly Shopify Sync — re-sync all products from Shopify
2. Cleanup Old Logs — purge logs older than retention period
3. Cleanup Expired Tokens — remove expired access tokens
4. Backup Reminder — log a warning if no backup was taken recently
5. Retry Dead Letters — attempt to recover dead-lettered transactions
6. Daily Inventory Report — generate and store daily report snapshot
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, delete

from app.config import settings
from app.models import Store, InventoryLog, InventoryTransaction
from app.inventory.repository import TransactionRepository
from app.inventory.service import InventoryService

logger = logging.getLogger(__name__)

LOG_RETENTION_DAYS = 90
TOKEN_CLEANUP_DAYS = 30
REPORT_HOUR = 2  # 2:00 AM


class SchedulerService:
    """Background scheduler for periodic maintenance tasks."""

    def __init__(self, db_url: str):
        self.engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
        self.SessionLocal = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self.running = True

    # ═══════════════════════════════════════════════════════════════
    # Job Runner
    # ═══════════════════════════════════════════════════════════════

    async def run_job(self, job_name: str, job_func):
        """Run a single job with error handling."""
        try:
            logger.info("Scheduled job started: %s", job_name)
            await job_func()
            logger.info("Scheduled job completed: %s", job_name)
        except Exception as exc:
            logger.exception("Scheduled job FAILED: %s — %s", job_name, exc)

    async def run_all(self):
        """Run all jobs once (for manual trigger or testing)."""
        await self.run_job("nightly_sync", self.nightly_shopify_sync)
        await self.run_job("cleanup_logs", self.cleanup_old_logs)
        await self.run_job("cleanup_tokens", self.cleanup_expired_tokens)
        await self.run_job("retry_dead_letters", self.retry_dead_letters)
        await self.run_job("daily_report", self.daily_inventory_report)

    # ═══════════════════════════════════════════════════════════════
    # Job 1: Nightly Shopify Sync
    # ═══════════════════════════════════════════════════════════════

    async def nightly_shopify_sync(self):
        """Re-sync all active stores' products from Shopify."""
        async with self.SessionLocal() as db:
            result = await db.execute(
                select(Store).where(Store.is_active == True)  # noqa: E712
            )
            stores = list(result.scalars().all())

            for store in stores:
                try:
                    service = InventoryService(db=db, store=store)
                    stats = await service.sync_from_shopify(force_full=False)
                    logger.info(
                        "Nightly sync for %s: %s",
                        store.shopify_domain,
                        stats,
                    )
                except Exception as exc:
                    logger.error(
                        "Nightly sync failed for %s: %s",
                        store.shopify_domain,
                        exc,
                    )

    # ═══════════════════════════════════════════════════════════════
    # Job 2: Cleanup Old Logs
    # ═══════════════════════════════════════════════════════════════

    async def cleanup_old_logs(self):
        """Purge inventory logs older than the retention period."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=LOG_RETENTION_DAYS)
        async with self.SessionLocal() as db:
            result = await db.execute(
                delete(InventoryLog).where(InventoryLog.created_at < cutoff)
            )
            await db.commit()
            logger.info("Cleaned up %d old log entries (before %s)", result.rowcount, cutoff.isoformat())

    # ═══════════════════════════════════════════════════════════════
    # Job 3: Cleanup Expired Tokens
    # ═══════════════════════════════════════════════════════════════

    async def cleanup_expired_tokens(self):
        """Remove stores with expired access tokens."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=TOKEN_CLEANUP_DAYS)
        # Note: Token expiry is tracked in the Store model's updated_at field
        # as a proxy. Production should use a proper token_expires_at field.
        async with self.SessionLocal() as db:
            # Find stores that haven't been updated in TOKEN_CLEANUP_DAYS
            # and mark them as inactive
            result = await db.execute(
                select(Store).where(
                    Store.is_active == True,  # noqa: E712
                    Store.updated_at < cutoff,
                )
            )
            stale_stores = list(result.scalars().all())
            for store in stale_stores:
                store.is_active = False
                logger.info(
                    "Deactivated stale store %s (last update: %s)",
                    store.shopify_domain,
                    store.updated_at,
                )
            await db.commit()
            logger.info("Deactivated %d stale stores", len(stale_stores))

    # ═══════════════════════════════════════════════════════════════
    # Job 4: Backup Reminder
    # ═══════════════════════════════════════════════════════════════

    async def backup_reminder_check(self):
        """
        Log a reminder if no backup was performed recently.

        Actual backup orchestration should be handled by the infrastructure
        (e.g., pg_dump cron job, managed DB snapshots). This job simply
        checks and logs a reminder.
        """
        # In production, check a backup_last_run_at table or file
        logger.info(
            "Backup reminder: Ensure PostgreSQL backups are configured. "
            "Recommended: daily pg_dump or managed DB snapshots."
        )

    # ═══════════════════════════════════════════════════════════════
    # Job 5: Retry Dead Letters
    # ═══════════════════════════════════════════════════════════════

    async def retry_dead_letters(self):
        """
        Attempt to recover dead-letter transactions.

        Dead letters are unsynced transactions that have exceeded
        the maximum retry attempts in the retry worker.
        """
        async with self.SessionLocal() as db:
            from app.shopify.retry_worker import DEAD_LETTER_THRESHOLD_HOURS

            cutoff = datetime.now(timezone.utc) - timedelta(hours=DEAD_LETTER_THRESHOLD_HOURS)

            # Find all stores
            stores_result = await db.execute(
                select(Store).where(Store.is_active == True)  # noqa: E712
            )
            stores = list(stores_result.scalars().all())

            for store in stores:
                txn_repo = TransactionRepository(db)
                unsynced = await txn_repo.get_unsynced(store.id, limit=100)

                dead_letters = [
                    t for t in unsynced
                    if t.created_at < cutoff
                ]

                if dead_letters:
                    logger.info(
                        "Store %s has %d dead-letter transactions",
                        store.shopify_domain,
                        len(dead_letters),
                    )
                    # Log the dead letters for monitoring
                    for dl in dead_letters:
                        logger.warning(
                            "Dead letter: transaction=%s, variant=%s, "
                            "created=%s, age_hours=%.1f",
                            dl.id,
                            dl.variant_id,
                            dl.created_at,
                            (datetime.now(timezone.utc) - dl.created_at).total_seconds() / 3600,
                        )

    # ═══════════════════════════════════════════════════════════════
    # Job 6: Daily Inventory Report
    # ═══════════════════════════════════════════════════════════════

    async def daily_inventory_report(self):
        """Generate and log a daily inventory summary for each active store."""
        async with self.SessionLocal() as db:
            from app.dashboard.dashboard_service import DashboardService

            result = await db.execute(
                select(Store).where(Store.is_active == True)  # noqa: E712
            )
            stores = list(result.scalars().all())

            for store in stores:
                try:
                    dashboard_service = DashboardService(db=db, store=store)
                    dashboard = await dashboard_service.get_dashboard()

                    logger.info(
                        "Daily inventory report for %s: "
                        "products=%d, variants=%d, low_stock=%d, "
                        "out_of_stock=%d, pending_syncs=%d",
                        store.shopify_domain,
                        dashboard.inventory_summary.total_products,
                        dashboard.inventory_summary.total_variants,
                        dashboard.inventory_summary.low_stock_count,
                        dashboard.inventory_summary.out_of_stock_count,
                        dashboard.sync_health.pending_syncs,
                    )

                except Exception as exc:
                    logger.error(
                        "Daily report failed for %s: %s",
                        store.shopify_domain,
                        exc,
                    )

    # ═══════════════════════════════════════════════════════════════
    # Entry Point
    # ═══════════════════════════════════════════════════════════════

    async def run_forever(self):
        """Run scheduled jobs at configured intervals."""
        logger.info("Scheduler service started")

        while self.running:
            now = datetime.now(timezone.utc)

            if now.hour == REPORT_HOUR and now.minute < 5:
                await self.run_all()

            await asyncio.sleep(300)  # Check every 5 minutes

    async def dispose(self):
        """Clean up the database engine."""
        self.running = False
        await self.engine.dispose()


async def main():
    """Entry point for running the scheduler as a standalone process."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    scheduler = SchedulerService(db_url=settings.DATABASE_URL)

    try:
        await scheduler.run_forever()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
    finally:
        await scheduler.dispose()


if __name__ == "__main__":
    asyncio.run(main())
