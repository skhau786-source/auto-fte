"""
Background retry worker for failed Shopify synchronizations.

Runs as an independent process (not a thread) that periodically queries
unsynced transactions and retries them with exponential backoff.

Usage:
    python -m app.inventory.retry_worker

Designed to be run as a separate container in docker-compose.prod.yml
so it doesn't block the API workers.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings
from app.inventory.shopify_client import ShopifyClient
from app.inventory.repository import TransactionRepository
from app.inventory.exceptions import ShopifySyncError
from app.models import Store, ProductVariant
from sqlalchemy import select

# ─── Constants ───

POLL_INTERVAL_SECONDS = settings.SYNC_RETRY_MINUTES * 60
MAX_RETRY_ATTEMPTS = 5
BASE_RETRY_DELAY_SECONDS = 10  # Initial backoff
DEAD_LETTER_THRESHOLD_HOURS = 24  # After 24h of failures, log as dead letter

logger = logging.getLogger(__name__)


class RetryWorker:
    """
    Periodically polls for unsynced transactions and retries the Shopify push.

    Flow:
        1. Query TransactionRepository.get_unsynced() for the store
        2. For each unsynced transaction:
           a. Look up the variant and store
           b. Create a ShopifyClient
           c. Call set_inventory_level
           d. If success: mark synced
           e. If failure: log and retry on next cycle
        3. Sleep POLL_INTERVAL_SECONDS
    """

    def __init__(self, db_url: str):
        self.engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
        self.SessionLocal = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self.running = True

    async def run_forever(self):
        """Main loop — runs until interrupted."""
        logger.info(
            "Retry worker started: poll_interval=%ds, max_retries=%d",
            POLL_INTERVAL_SECONDS,
            MAX_RETRY_ATTEMPTS,
        )

        while self.running:
            try:
                await self._process_cycle()
            except Exception as exc:
                logger.exception("Unhandled error in retry cycle: %s", exc)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _process_cycle(self):
        """Single poll cycle — process all unsynced transactions."""
        async with self.SessionLocal() as db:
            txn_repo = TransactionRepository(db)

            # Get all active stores
            stores_result = await db.execute(
                select(Store).where(Store.is_active == True)  # noqa: E712
            )
            stores = list(stores_result.scalars().all())

            for store in stores:
                try:
                    unsynced = await txn_repo.get_unsynced(store.id, limit=50)
                    if not unsynced:
                        continue

                    logger.info(
                        "Store %s: %d unsynced transactions to retry",
                        store.shopify_domain,
                        len(unsynced),
                    )

                    for txn in unsynced:
                        await self._retry_transaction(db, store, txn)

                    await db.commit()
                except Exception as exc:
                    logger.exception(
                        "Error processing store %s: %s",
                        store.shopify_domain,
                        exc,
                    )
                    await db.rollback()

    async def _retry_transaction(
        self,
        db: AsyncSession,
        store: Store,
        transaction: "InventoryTransaction",
    ) -> None:
        """
        Attempt to push a single unsynced transaction to Shopify.

        Uses exponential backoff: the nth retry waits BASE_RETRY_DELAY * 2^n seconds.
        After MAX_RETRY_ATTEMPTS, the transaction is logged as a dead letter.
        """
        from app.models import InventoryTransaction
        txn_repo = TransactionRepository(db)

        # Check retry count (using created_at as proxy — each cycle = 1 retry)
        hours_since_creation = (
            datetime.now(timezone.utc) - transaction.created_at
        ).total_seconds() / 3600

        estimated_attempts = int(
            (datetime.now(timezone.utc) - transaction.created_at).total_seconds()
            / POLL_INTERVAL_SECONDS
        )

        if estimated_attempts >= MAX_RETRY_ATTEMPTS:
            logger.warning(
                "Dead letter: transaction %s exceeded %d retry attempts. "
                "Created at %s, last attempt at %s. Skipping.",
                transaction.id,
                MAX_RETRY_ATTEMPTS,
                transaction.created_at,
                datetime.now(timezone.utc),
            )
            return

        # Look up the variant and its inventory_item_id
        variant_result = await db.execute(
            select(ProductVariant).where(ProductVariant.id == transaction.variant_id)
        )
        variant = variant_result.scalar_one_or_none()

        if variant is None:
            logger.warning(
                "Dead letter: variant %s not found for transaction %s",
                transaction.variant_id,
                transaction.id,
            )
            return

        if not variant.shopify_inventory_item_id:
            logger.warning(
                "Dead letter: variant %s has no Shopify inventory_item_id",
                variant.id,
            )
            return

        if not store.shopify_location_id:
            logger.warning(
                "Dead letter: store %s has no location_id",
                store.shopify_domain,
            )
            return

        # Compute backoff delay
        backoff_seconds = BASE_RETRY_DELAY_SECONDS * (2 ** estimated_attempts)
        logger.info(
            "Retrying sync: transaction=%s, variant=%s, "
            "inventory_item=%d, qty=%d, attempt=%d, backoff=%ds",
            transaction.id,
            variant.id,
            variant.shopify_inventory_item_id,
            transaction.quantity_after,
            estimated_attempts + 1,
            backoff_seconds,
        )

        client = ShopifyClient(
            shop_domain=store.shopify_domain,
            access_token=store.access_token,
            location_id=store.shopify_location_id,
        )

        try:
            await client.set_inventory_level(
                inventory_item_id=variant.shopify_inventory_item_id,
                location_id=store.shopify_location_id,
                quantity=transaction.quantity_after,
            )

            # Mark as synced
            await txn_repo.mark_synced(transaction.id)
            logger.info(
                "Retry succeeded: transaction %s synced to Shopify",
                transaction.id,
            )

        except ShopifySyncError as exc:
            logger.warning(
                "Retry failed: transaction %s, error=%s. "
                "Will retry in %ds (attempt %d/%d)",
                transaction.id,
                exc,
                POLL_INTERVAL_SECONDS,
                estimated_attempts + 1,
                MAX_RETRY_ATTEMPTS,
            )

            # Dead letter check
            if hours_since_creation >= DEAD_LETTER_THRESHOLD_HOURS:
                logger.error(
                    "DEAD LETTER: transaction %s has been failing for %.1f hours. "
                    "Manual intervention may be required.",
                    transaction.id,
                    hours_since_creation,
                )
        except Exception as exc:
            logger.exception(
                "Unexpected error during retry for transaction %s: %s",
                transaction.id,
                exc,
            )
        finally:
            await client.close()


async def main():
    """Entry point — configures logging and starts the worker."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    worker = RetryWorker(db_url=settings.DATABASE_URL)

    try:
        await worker.run_forever()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    finally:
        worker.running = False
        await worker.engine.dispose()
        logger.info("Worker shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
