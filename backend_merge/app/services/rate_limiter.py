"""
Simple in-memory rate limiter - login brute-force se bachne ke liye.

Note: Single instance ke liye theek hai. Agar app multiple servers par
chalti ho to Redis-based limiter use karna (team member wala design).
"""
import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import HTTPException, Request

from app.config import settings

_attempts: dict[str, Deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    """Reverse proxy (nginx/cloudflare) ke piche bhi sahi IP nikalta hai."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def login_rate_limiter(request: Request) -> None:
    """
    Har IP par limited attempts - window ke andar zyada try karne par 429.
    Login, signup aur forgot-password par use karo.
    """
    ip = _client_ip(request)
    now = time.time()
    q = _attempts[ip]

    # purane attempts hatao (window se bahar wale)
    while q and now - q[0] > settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS:
        q.popleft()

    if len(q) >= settings.RATE_LIMIT_LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Kuch der baad dobara try karein.",
        )

    q.append(now)
