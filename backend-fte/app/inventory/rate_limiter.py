"""
In-memory sliding window rate limiter.

No external dependencies required (no Redis needed).
Uses a simple sliding window algorithm per IP address.

Configuration:
    RATE_LIMIT_PER_MINUTE: int (default 60)
    RATE_LIMIT_WHITELIST: str = comma-separated IPs (default "127.0.0.1,localhost")
"""

import time
import logging
from collections import defaultdict
from typing import Optional

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger(__name__)

# ─── In-memory store ───
# Format: {ip_address: [timestamp1, timestamp2, ...]}
_window_store: dict[str, list[float]] = defaultdict(list)

# How often (in seconds) to clean up expired entries
_CLEANUP_INTERVAL = 60
_last_cleanup: float = 0.0


class RateLimitExceeded(HTTPException):
    def __init__(self, retry_after: int):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": "Rate limit exceeded. Please slow down.",
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )


def _get_client_ip(request: Request) -> str:
    """Extract the client IP from headers or connection info."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    # Fall back to the client host
    client = request.client
    if client:
        return client.host
    return "unknown"


def _is_whitelisted(ip: str) -> bool:
    """Check if an IP is whitelisted (no rate limit)."""
    whitelist_raw = getattr(settings, "RATE_LIMIT_WHITELIST", "127.0.0.1,localhost")
    whitelist = [w.strip() for w in whitelist_raw.split(",")]
    return ip in whitelist


def _cleanup_expired(window_seconds: int) -> None:
    """Remove timestamps older than the window from the store."""
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    cutoff = now - window_seconds
    for ip in list(_window_store.keys()):
        _window_store[ip] = [ts for ts in _window_store[ip] if ts > cutoff]
        if not _window_store[ip]:
            del _window_store[ip]
    _last_cleanup = now


def _check_rate_limit(ip: str, max_requests: int, window_seconds: int) -> Optional[int]:
    """
    Check if the IP has exceeded the rate limit.

    Returns:
        None if within limit, or the number of seconds to wait before retrying.
    """
    now = time.time()
    cutoff = now - window_seconds

    # Get timestamps still within the window
    timestamps = _window_store[ip]
    timestamps = [ts for ts in timestamps if ts > cutoff]
    _window_store[ip] = timestamps

    if len(timestamps) >= max_requests:
        # How long until the oldest request falls out of the window
        oldest = min(timestamps)
        retry_after = int(window_seconds - (now - oldest) + 1)
        return max(retry_after, 1)

    # Record this request
    _window_store[ip].append(now)
    return None


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that rate-limits requests per IP.

    Uses a sliding window (default 60 seconds) with configurable max requests.
    Localhost/127.0.0.1 is always whitelisted.

    Configure via env vars:
        RATE_LIMIT_PER_MINUTE=60
    """

    def __init__(
        self,
        app,
        max_requests: Optional[int] = None,
        window_seconds: int = 60,
    ):
        super().__init__(app)
        self.max_requests = max_requests or settings.RATE_LIMIT_PER_MINUTE
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for health/monitoring endpoints
        if request.url.path in ("/health", "/ready", "/live", "/version", "/metrics"):
            return await call_next(request)

        ip = _get_client_ip(request)

        if not _is_whitelisted(ip):
            retry_after = _check_rate_limit(ip, self.max_requests, self.window_seconds)
            if retry_after is not None:
                logger.warning(
                    "Rate limit exceeded: ip=%s, path=%s, retry_after=%ds",
                    ip,
                    request.url.path,
                    retry_after,
                )
                raise RateLimitExceeded(retry_after=retry_after)

        # Periodic cleanup (runs at most once per minute)
        _cleanup_expired(self.window_seconds)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, self.max_requests - len(_window_store.get(ip, [])))
        )
        return response
