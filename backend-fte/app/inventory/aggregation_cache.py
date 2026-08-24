"""
Inventory Aggregation Cache — store-scoped.

Lightweight in-memory TTL cache for aggregation responses.

Design:
- Uses a simple dict with expiry timestamps
- Configurable default TTL (default 60 seconds)
- get/set/delete/clear/clear_prefix operations
- Specialized invalidate_store() method
- Will NOT cache errors (None/empty results)
- Abstraction allows future Redis replacement (same interface)

Thread safety:
- All operations use a single lock to prevent race conditions
- Expired entries are lazily evicted on get()

Cache keys follow the pattern:
  agg:store:{store_id}
  agg:dashboard:{store_id}
  agg:product:{store_id}:{product_id}
  agg:variant:{store_id}:{variant_id}
  agg:reports:{store_id}
"""

from __future__ import annotations

import time
import uuid
import logging
from threading import Lock
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default TTL in seconds
DEFAULT_CACHE_TTL = 60


class InventoryAggregationCache:
    """
    In-memory TTL cache for inventory aggregation responses.

    Usage:
        cache = InventoryAggregationCache(default_ttl=60)
        await cache.set("agg:store:...", data)
        data = await cache.get("agg:store:...")
        await cache.invalidate_store(store_id)
    """

    def __init__(self, default_ttl: int = DEFAULT_CACHE_TTL):
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = Lock()
        self.default_ttl = default_ttl
        self._hit_count = 0
        self._miss_count = 0
        self.logger = logging.getLogger(f"{__name__}.InventoryAggregationCache")

    # ── Public API ──────────────────────────────────────────────

    async def get(self, key: str) -> Optional[Any]:
        """
        Get a cached value by key.

        Returns None if:
        - Key doesn't exist
        - Entry has expired (lazy eviction)
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._miss_count += 1
                return None

            expires_at, value = entry
            if time.monotonic() > expires_at:
                # Lazy eviction
                del self._cache[key]
                self._miss_count += 1
                return None

            self._hit_count += 1
            return value

    async def set(
        self, key: str, value: Any, ttl: Optional[int] = None,
    ) -> None:
        """
        Cache a value by key with optional TTL override.

        Will NOT cache:
        - None values
        - Empty dicts (no data)
        - Error responses (is_error=True markers)

        This prevents serving stale error responses.
        """
        # Never cache falsy aggregation data or errors
        if value is None:
            return
        if isinstance(value, dict) and not value:
            return
        if isinstance(value, dict) and value.get("_error", False):
            return

        ttl_seconds = ttl if ttl is not None else self.default_ttl
        expires_at = time.monotonic() + ttl_seconds

        with self._lock:
            self._cache[key] = (expires_at, value)

    async def delete(self, key: str) -> bool:
        """Delete a specific cache key. Returns True if existed."""
        with self._lock:
            existed = key in self._cache
            self._cache.pop(key, None)
            return existed

    async def clear(self) -> int:
        """Clear ALL cached entries. Returns count of cleared entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    async def clear_prefix(self, prefix: str) -> int:
        """
        Clear all cache entries whose key starts with a given prefix.

        Example: clear_prefix("agg:store:123") clears all store-level caches.

        Returns count of cleared entries.
        """
        with self._lock:
            keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_delete:
                del self._cache[key]
            return len(keys_to_delete)

    # ── Specialized Invalidation ────────────────────────────────

    async def invalidate_store(self, store_id: uuid.UUID) -> int:
        """
        Invalidate ALL cache entries for a store.

        This is called whenever any inventory-changing operation occurs
        (reservation, allocation, sync, manual update, product CRUD).

        Clears:
        - agg:store:{store_id}        (store-level totals)
        - agg:dashboard:{store_id}    (dashboard widget summary)
        - agg:product:{store_id}:*    (per-product aggregates)
        - agg:variant:{store_id}:*    (per-variant aggregates)
        - agg:reports:{store_id}      (report data)

        Returns count of cleared entries.
        """
        count = await self.clear_prefix(f"agg:product:{store_id}:")
        count += await self.clear_prefix(f"agg:variant:{store_id}:")
        count += await self.delete(f"agg:store:{store_id}")
        count += await self.delete(f"agg:dashboard:{store_id}")
        count += await self.delete(f"agg:reports:{store_id}")

        if count > 0:
            self.logger.debug(
                "Invalidated %d cache entries for store %s", count, store_id,
            )

        return count

    # ── Key Builders ────────────────────────────────────────────

    @staticmethod
    def key_store(store_id: uuid.UUID) -> str:
        return f"agg:store:{store_id}"

    @staticmethod
    def key_dashboard(store_id: uuid.UUID) -> str:
        return f"agg:dashboard:{store_id}"

    @staticmethod
    def key_product(store_id: uuid.UUID, product_id: uuid.UUID) -> str:
        return f"agg:product:{store_id}:{product_id}"

    @staticmethod
    def key_variant(store_id: uuid.UUID, variant_id: uuid.UUID) -> str:
        return f"agg:variant:{store_id}:{variant_id}"

    @staticmethod
    def key_reports(store_id: uuid.UUID) -> str:
        return f"agg:reports:{store_id}"

    # ── Stats ───────────────────────────────────────────────────

    @property
    def stats(self) -> dict:
        """Return cache statistics for monitoring."""
        with self._lock:
            return {
                "size": len(self._cache),
                "hit_count": self._hit_count,
                "miss_count": self._miss_count,
                "hit_ratio": round(
                    self._hit_count / (self._hit_count + self._miss_count), 3,
                ) if (self._hit_count + self._miss_count) > 0 else 0.0,
                "default_ttl": self.default_ttl,
            }


# Module-level singleton cache instance
# Imported by services for cache invalidation after mutations.
# Can be replaced with Redis by changing this line.
aggregation_cache = InventoryAggregationCache(default_ttl=DEFAULT_CACHE_TTL)
