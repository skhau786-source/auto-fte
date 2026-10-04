"""
Sliding-window rate limiter (in-memory, per process).

Public endpoints ke liye: key (IP / session) ke hisaab se "limit hits per window seconds".
Clock inject ho sakta hai (tests). Multi-worker deployment mein har process ka apna counter
hota hai — shared limit chahiye to Redis-backed limiter se badalna hoga.
"""

import math
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Optional

from fastapi import Request


class SlidingWindowLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._hits: dict[str, Deque[float]] = defaultdict(deque)
        self._calls = 0

    def hit(self, key: str, limit: int, window_seconds: float) -> tuple[bool, int]:
        """Hit record karo. (allowed, retry_after_seconds) return hota hai."""
        now = self._clock()
        q = self._hits[key]
        while q and now - q[0] >= window_seconds:
            q.popleft()

        if len(q) >= limit:
            return False, max(1, math.ceil(window_seconds - (now - q[0])))

        q.append(now)
        self._calls += 1
        if self._calls % 500 == 0:
            self._gc(now, window_seconds)
        return True, 0

    def _gc(self, now: float, window_seconds: float) -> None:
        """Khali / purani keys hata do (memory na barhe)."""
        for key in [k for k, q in self._hits.items() if not q or now - q[-1] >= window_seconds]:
            del self._hits[key]

    def reset(self) -> None:
        self._hits.clear()


def client_ip(request: Request, trust_proxy_headers: bool = False) -> str:
    """Client ka IP. X-Forwarded-For sirf tab mana jata hai jab trusted proxy ho
    (rightmost entry: woh jo hamare proxy ne jori; leftmost client ka likha hua hota hai)."""
    if trust_proxy_headers:
        forwarded: Optional[str] = request.headers.get("X-Forwarded-For")
        if forwarded:
            last = forwarded.split(",")[-1].strip()
            if last:
                return last
    return request.client.host if request.client else "unknown"
