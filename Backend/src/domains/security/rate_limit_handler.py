"""
429 exception handler.

main.py ne status code 429 par slowapi ka handler lagaya tha. Woh sirf slowapi ki apni
RateLimitExceeded samajhta hai; koi bhi plain HTTPException(429) (login limiter, public chat
limiter) usme AttributeError deke 500 ban jata tha. Yeh wrapper dono ko sambhalta hai.
"""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded


async def handle_429(request: Request, exc: Exception):
    if isinstance(exc, RateLimitExceeded):
        return _rate_limit_exceeded_handler(request, exc)

    detail = exc.detail if isinstance(exc, HTTPException) else "Too many requests."
    headers = getattr(exc, "headers", None) or {}
    return JSONResponse(status_code=429, content={"detail": detail}, headers=headers)
