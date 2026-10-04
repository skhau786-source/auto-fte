from src.domains.ecommerce.routes import router as routes_router
from src.domains.ecommerce.webhooks import router as webhooks_router
from src.domains.ecommerce.oauth import router as oauth_router
from src.domains.ecommerce.inventory_routes import router as inventory_router
from src.domains.ecommerce.reservation_routes import router as reservation_router

__all__ = [
    "routes_router", "webhooks_router", "oauth_router",
    "inventory_router", "reservation_router",
]
