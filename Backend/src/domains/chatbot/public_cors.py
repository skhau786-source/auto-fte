# ═══════════════════════════════════════════════════════════════
# domains / chatbot / public_cors.py
#
# PURPOSE: /api/v1/public/* ke liye CORS: store ki website kisi bhi origin par ho sakti hai.
#          Cookies/credentials istemal nahi hote (visitor token header mein hota hai), isliye
#          Access-Control-Allow-Origin: * mehfooz hai. Baqi API ki CORS policy waisi hi rehti hai.
# ═══════════════════════════════════════════════════════════════

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

PUBLIC_PREFIX = "/api/v1/public/"

_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Visitor-Session",
    "Access-Control-Expose-Headers": "Retry-After",
    "Access-Control-Max-Age": "600",
}


class PublicCorsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith(PUBLIC_PREFIX):
            return await call_next(request)

        if request.method == "OPTIONS":
            return Response(status_code=204, headers=_HEADERS)

        response = await call_next(request)
        for name, value in _HEADERS.items():
            response.headers[name] = value
        return response
