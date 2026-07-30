"""
Webhook Queue for WooCommerce Integration Module.

Provides asynchronous webhook processing via Celery with:
- Redis-backed webhook queue
- Retry queue with exponential backoff
- Dead letter queue for permanently failed webhooks
- Queue depth monitoring
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from dataclasses import dataclass, field, asdict

from app.config import settings

logger = logging.getLogger(__name__)

# Redis key prefixes
WEBHOOK_QUEUE_PREFIX = "wc_webhook_queue:"
RETRY_QUEUE_PREFIX = "wc_webhook_retry:"
DEAD_LETTER_QUEUE_PREFIX = "wc_webhook_dlq:"
QUEUE_DEPTH_KEY = "wc_webhook_queue_depth"


@dataclass
class QueuedWebhook:
    """A webhook event queued for asynchronous processing."""

    topic: str
    store_id: str
    resource_id: Optional[int] = None
    payload: dict = field(default_factory=dict)
    source_url: str = ""
    signature: str = ""
    idempotency_key: str = ""
    retry_count: int = 0
    max_retries: int = 3
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_expired(self) -> bool:
        """Check if this webhook has exceeded max retries."""
        return self.retry_count >= self.max_retries

    def next_retry_delay(self) -> int:
        """Calculate exponential backoff delay in seconds."""
        base_delay = 60  # 1 minute base
        return base_delay * (2 ** self.retry_count)  # 1min, 2min, 4min


class WebhookQueue:
    """
    Async webhook queue manager backed by Redis (with fallback to in-memory).

    Manages three queues:
    - Main queue: Webhooks awaiting processing
    - Retry queue: Webhooks that failed and will be retried
    - Dead letter queue: Webhooks that exceeded max retries
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._in_memory_queue: list[QueuedWebhook] = []
        self._in_memory_retry: list[QueuedWebhook] = []
        self._in_memory_dlq: list[QueuedWebhook] = []
        self.logger = logging.getLogger(f"{__name__}.WebhookQueue")

    @property
    def _use_redis(self) -> bool:
        """Check if Redis is available for queue storage."""
        return self._redis is not None

    # ═══════════════════════════════════════════════════════════════
    # QUEUE OPERATIONS
    # ═══════════════════════════════════════════════════════════════

    async def enqueue(self, webhook: QueuedWebhook) -> bool:
        """
        Add a webhook to the main processing queue.

        Args:
            webhook: The webhook event to enqueue

        Returns:
            True if enqueued successfully
        """
        if self._use_redis:
            try:
                key = f"{WEBHOOK_QUEUE_PREFIX}{webhook.idempotency_key or webhook.created_at}"
                await self._redis.setex(key, 3600, json.dumps(asdict(webhook)))
                await self._redis.incr(QUEUE_DEPTH_KEY)
                return True
            except Exception as exc:
                self.logger.warning("Redis enqueue failed, falling back to memory: %s", exc)

        self._in_memory_queue.append(webhook)
        return True

    async def dequeue(self) -> Optional[QueuedWebhook]:
        """
        Dequeue the next webhook for processing.

        Returns:
            The next webhook to process, or None if queue is empty
        """
        if self._use_redis:
            try:
                keys = await self._redis.keys(f"{WEBHOOK_QUEUE_PREFIX}*")
                if keys:
                    key = keys[0]
                    data = await self._redis.get(key)
                    await self._redis.delete(key)
                    await self._redis.decr(QUEUE_DEPTH_KEY)
                    if data:
                        return QueuedWebhook(**json.loads(data))
            except Exception as exc:
                self.logger.warning("Redis dequeue failed: %s", exc)

        if self._in_memory_queue:
            return self._in_memory_queue.pop(0)
        return None

    async def queue_size(self) -> int:
        """Get the current size of the main queue."""
        if self._use_redis:
            try:
                depth = await self._redis.get(QUEUE_DEPTH_KEY)
                return int(depth) if depth else 0
            except Exception:
                pass
        return len(self._in_memory_queue)

    # ═══════════════════════════════════════════════════════════════
    # RETRY QUEUE
    # ═══════════════════════════════════════════════════════════════

    async def enqueue_retry(self, webhook: QueuedWebhook) -> bool:
        """
        Move a failed webhook to the retry queue.

        The webhook's retry_count is incremented and it will be
        retried after exponential backoff.
        """
        webhook.retry_count += 1

        if webhook.is_expired:
            return await self.enqueue_dead_letter(webhook)

        delay = webhook.next_retry_delay()

        if self._use_redis:
            try:
                key = f"{RETRY_QUEUE_PREFIX}{webhook.idempotency_key}"
                await self._redis.setex(key, delay, json.dumps(asdict(webhook)))
                self.logger.info(
                    "Webhook queued for retry in %ds: topic=%s, retry=%d/%d",
                    delay, webhook.topic, webhook.retry_count, webhook.max_retries,
                )
                return True
            except Exception as exc:
                self.logger.warning("Redis retry enqueue failed: %s", exc)

        self._in_memory_retry.append(webhook)
        return True

    async def dequeue_retry(self) -> Optional[QueuedWebhook]:
        """Dequeue the next webhook from the retry queue."""
        if self._use_redis:
            try:
                keys = await self._redis.keys(f"{RETRY_QUEUE_PREFIX}*")
                if keys:
                    key = keys[0]
                    data = await self._redis.get(key)
                    await self._redis.delete(key)
                    if data:
                        return QueuedWebhook(**json.loads(data))
            except Exception:
                pass

        if self._in_memory_retry:
            return self._in_memory_retry.pop(0)
        return None

    async def retry_queue_size(self) -> int:
        """Get the size of the retry queue."""
        if self._use_redis:
            try:
                keys = await self._redis.keys(f"{RETRY_QUEUE_PREFIX}*")
                return len(keys)
            except Exception:
                pass
        return len(self._in_memory_retry)

    # ═══════════════════════════════════════════════════════════════
    # DEAD LETTER QUEUE
    # ═══════════════════════════════════════════════════════════════

    async def enqueue_dead_letter(self, webhook: QueuedWebhook) -> bool:
        """
        Move a permanently failed webhook to the dead letter queue.
        """
        self.logger.warning(
            "Webhook moved to DLQ: topic=%s, store=%s, retries=%d",
            webhook.topic, webhook.store_id, webhook.retry_count,
        )

        if self._use_redis:
            try:
                key = f"{DEAD_LETTER_QUEUE_PREFIX}{webhook.idempotency_key}"
                await self._redis.setex(key, 86400 * 7, json.dumps(asdict(webhook)))
                return True
            except Exception as exc:
                self.logger.warning("Redis DLQ enqueue failed: %s", exc)

        self._in_memory_dlq.append(webhook)
        return True

    async def dead_letter_queue_size(self) -> int:
        """Get the size of the dead letter queue."""
        if self._use_redis:
            try:
                keys = await self._redis.keys(f"{DEAD_LETTER_QUEUE_PREFIX}*")
                return len(keys)
            except Exception:
                pass
        return len(self._in_memory_dlq)

    async def get_dead_letters(self, limit: int = 50) -> list[QueuedWebhook]:
        """Get items from the dead letter queue."""
        if self._use_redis:
            try:
                keys = await self._redis.keys(f"{DEAD_LETTER_QUEUE_PREFIX}*")
                items = []
                for key in keys[:limit]:
                    data = await self._redis.get(key)
                    if data:
                        items.append(QueuedWebhook(**json.loads(data)))
                return items
            except Exception:
                pass
        return self._in_memory_dlq[:limit]

    # ═══════════════════════════════════════════════════════════════
    # QUEUE METRICS
    # ═══════════════════════════════════════════════════════════════

    async def get_metrics(self) -> dict:
        """
        Get comprehensive queue metrics for the dashboard.

        Returns:
            Dict with queue sizes and status counts
        """
        return {
            "queue_size": await self.queue_size(),
            "retry_queue_size": await self.retry_queue_size(),
            "dead_letter_queue_size": await self.dead_letter_queue_size(),
            "total_pending": await self.queue_size() + await self.retry_queue_size(),
        }
