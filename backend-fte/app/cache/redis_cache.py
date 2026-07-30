"""
Redis Cache Service — caching layer for frequently accessed data.

Cached items:
- Dashboard (store dashboard)
- Categories (store categories)
- Products (product list)
- Inventory Summary (dashboard stats)
- Store Settings (store configuration)

Features:
- Automatic invalidation on write operations
- Configurable TTL per cache type
- Manual purge by pattern
- Graceful fallback when Redis is unavailable
"""

import json
import logging
import uuid
from typing import Optional, Any
from datetime import timedelta, datetime

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Default TTLs (seconds) ───

DEFAULT_TTL_SECONDS = {
    "dashboard": 60,          # 1 minute
    "categories": 300,        # 5 minutes
    "products": 60,           # 1 minute
    "inventory_summary": 60,  # 1 minute
    "store_settings": 600,    # 10 minutes
}


class CacheService:
    """
    Redis-based cache service.

    All methods are designed to be safe to call when Redis is not configured —
    they log a warning and return None / no-op.

    Usage:
        cache = CacheService()
        await cache.set("products:store:{id}", data, ttl=120)
        data = await cache.get("products:store:{id}")
        await cache.flush_pattern("products:*")
        await cache.close()
    """

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._client = None
        self._connected = self._check_configured()

    def _check_configured(self) -> bool:
        """Check if Redis is configured and reachable."""
        if not self.redis_url:
            return False
        # Skip the default URL check — if it's explicitly configured, try to use it
        return True

    async def _get_client(self):
        """Lazy-init the Redis client."""
        if self._client is not None:
            return self._client
        if not self._connected:
            return None

        try:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(
                self.redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=True,
            )
            await self._client.ping()
            return self._client
        except Exception as exc:
            logger.debug("Redis not available: %s", exc)
            self._connected = False
            self._client = None
            return None

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from cache by key."""
        client = await self._get_client()
        if client is None:
            return None

        try:
            value = await client.get(key)
            if value is not None:
                return json.loads(value)
            return None
        except Exception as exc:
            logger.debug("Cache GET failed for %s: %s", key, exc)
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        cache_type: Optional[str] = None,
    ) -> bool:
        """Set a value in cache with optional TTL."""
        client = await self._get_client()
        if client is None:
            return False

        if ttl is None and cache_type:
            ttl = DEFAULT_TTL_SECONDS.get(cache_type, 60)

        try:
            serialized = json.dumps(value, default=str)
            if ttl:
                await client.setex(key, ttl, serialized)
            else:
                await client.set(key, serialized)
            return True
        except Exception as exc:
            logger.debug("Cache SET failed for %s: %s", key, exc)
            return False

    async def delete(self, key: str) -> bool:
        """Delete a specific key from cache."""
        client = await self._get_client()
        if client is None:
            return False

        try:
            await client.delete(key)
            return True
        except Exception as exc:
            logger.debug("Cache DELETE failed for %s: %s", key, exc)
            return False

    async def flush_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern (e.g., 'store:*:dashboard')."""
        client = await self._get_client()
        if client is None:
            return 0

        try:
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = await client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    await client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            if deleted > 0:
                logger.info("Cache flushed %d keys matching '%s'", deleted, pattern)
            return deleted
        except Exception as exc:
            logger.debug("Cache FLUSH failed for pattern %s: %s", pattern, exc)
            return 0

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        client = await self._get_client()
        if client is None:
            return False

        try:
            return await client.exists(key) > 0
        except Exception:
            return False

    async def close(self):
        """Close the Redis connection."""
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    # ═══════════════════════════════════════════════════════════════
    # Convenience: Cache Keys
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def dashboard_key(store_id: uuid.UUID) -> str:
        return f"store:{store_id}:dashboard"

    @staticmethod
    def categories_key(store_id: uuid.UUID) -> str:
        return f"store:{store_id}:categories"

    @staticmethod
    def products_key(store_id: uuid.UUID) -> str:
        return f"store:{store_id}:products"

    @staticmethod
    def inventory_summary_key(store_id: uuid.UUID) -> str:
        return f"store:{store_id}:inventory_summary"

    @staticmethod
    def store_settings_key(store_id: uuid.UUID) -> str:
        return f"store:{store_id}:settings"

    # ═══════════════════════════════════════════════════════════════
    # Convenience: Auto-Cache Decorator Pattern
    # ═══════════════════════════════════════════════════════════════

    async def get_or_set(
        self,
        key: str,
        factory,
        ttl: Optional[int] = None,
        cache_type: Optional[str] = None,
    ) -> Any:
        """
        Get from cache, or call factory() to populate and cache.

        Usage:
            data = await cache.get_or_set(
                key=CacheService.dashboard_key(store.id),
                factory=lambda: dashboard_service.get_dashboard(),
                cache_type="dashboard",
            )
        """
        cached = await self.get(key)
        if cached is not None:
            return cached

        value = await factory()
        await self.set(key, value, ttl=ttl, cache_type=cache_type)
        return value

    async def invalidate_store(self, store_id: uuid.UUID) -> int:
        """Invalidate ALL cache entries for a store."""
        return await self.flush_pattern(f"store:{store_id}:*")


# ═══════════════════════════════════════════════════════════════════
# Global Cache Instance
# ═══════════════════════════════════════════════════════════════════

_default_cache: Optional[CacheService] = None


def get_cache() -> CacheService:
    """Get or create the default cache service instance."""
    global _default_cache
    if _default_cache is None:
        _default_cache = CacheService()
    return _default_cache
