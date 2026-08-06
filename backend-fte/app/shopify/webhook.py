"""
Shopify Webhook Router for the Shopify integration module.

All webhooks are verified using HMAC-SHA256 before processing.
The router is thin — all business logic lives in InventoryService.
Webhooks return HTTP 200 immediately after processing (no polling).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Store
from app.shopify.shopify_client import ShopifyClient
from app.inventory.service import InventoryService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Shopify Webhooks"])


# ═══════════════════════════════════════════════════════════════════
# Webhook Verification Dependency
# ═══════════════════════════════════════════════════════════════════


async def _verify_and_get_store(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Store:
    """
    Verify the HMAC signature of a Shopify webhook and return the store.

    Extracts the raw body and headers from the request, computes the HMAC,
    and looks up the store by shop domain.

    Raises:
        401: If the HMAC signature is missing or invalid.
        404: If no active store is found for the shop domain.
    """
    body = await request.body()
    hmac_header = request.headers.get("x-shopify-hmac-sha256", "")
    shop_domain = request.headers.get("x-shopify-shop-domain", "")

    # ── Validate header presence ──
    if not hmac_header:
        logger.warning("Webhook rejected: missing HMAC header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Shopify-Hmac-Sha256 header",
        )

    if not shop_domain:
        logger.warning("Webhook rejected: missing shop domain header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Shopify-Shop-Domain header",
        )

    # ── Verify HMAC signature ──
    if not ShopifyClient.verify_webhook(
        hmac_header=hmac_header,
        body=body,
        client_secret=settings.SHOPIFY_API_SECRET,
    ):
        logger.warning("Webhook rejected: invalid HMAC signature for %s", shop_domain)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    # ── Look up the store ──
    result = await db.execute(
        select(Store).where(
            Store.shopify_domain == shop_domain,
            Store.is_active == True,  # noqa: E712
        )
    )
    store = result.scalar_one_or_none()

    if store is None:
        logger.warning(
            "Webhook from unknown or inactive store: %s",
            shop_domain,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found or inactive",
        )

    return store


# ═══════════════════════════════════════════════════════════════════
# POST /webhooks/inventory-levels-update
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/inventory-levels-update",
    summary="Handle inventory level update from Shopify",
    description="Triggered when inventory levels change in Shopify. Updates local variant quantity without pushing back.",
)
async def handle_inventory_levels_update(
    request: Request,
    store: Store = Depends(_verify_and_get_store),
    db: AsyncSession = Depends(get_db),
):
    """
    Shopify webhook: `inventory_levels/update`

    Payload:
        {
            "inventory_item_id": 808950810,
            "location_id": 905684977,
            "available": 25,
            "updated_at": "2024-01-15T10:00:00-05:00"
        }

    Flow:
        1. HMAC signature verified by _verify_and_get_store
        2. Parse payload for inventory_item_id, location_id, available
        3. Call InventoryService.update_inventory_from_webhook()
        4. Return 200 OK (no polling)
    """
    topic = request.headers.get("x-shopify-topic", "unknown")
    logger.info(
        "Webhook received: topic=%s, shop=%s, id=%s",
        topic,
        store.shopify_domain,
        store.id,
    )

    payload = await request.json()
    inventory_item_id = payload.get("inventory_item_id")
    location_id = payload.get("location_id")
    new_quantity = payload.get("available")

    if inventory_item_id is None or new_quantity is None:
        logger.warning(
            "Invalid inventory_levels/update payload from %s: %s",
            store.shopify_domain,
            payload,
        )
        return {"status": "ok", "result": "ignored_invalid_payload"}

    service = InventoryService(db=db, store=store)
    result = await service.update_inventory_from_webhook(
        inventory_item_id=inventory_item_id,
        location_id=location_id,
        new_quantity=new_quantity,
    )

    logger.info(
        "Webhook processed: topic=%s, variant=%s, result=%s",
        topic,
        result.get("variant_id"),
        result.get("status"),
    )
    return {"status": "ok", "result": result}


# ═══════════════════════════════════════════════════════════════════
# POST /webhooks/products-update
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/products-update",
    summary="Handle product update from Shopify",
    description="Triggered when a product is created or updated in Shopify. Upserts the product and its variants locally.",
)
async def handle_products_update(
    request: Request,
    store: Store = Depends(_verify_and_get_store),
    db: AsyncSession = Depends(get_db),
):
    """
    Shopify webhook: `products/update`

    Payload:
        Full product object with nested variants (see Shopify docs).

    Flow:
        1. HMAC signature verified by _verify_and_get_store
        2. Pass the full payload to InventoryService.update_product_from_webhook()
        3. Return 200 OK
    """
    topic = request.headers.get("x-shopify-topic", "unknown")
    logger.info(
        "Webhook received: topic=%s, shop=%s, id=%s",
        topic,
        store.shopify_domain,
        store.id,
    )

    payload = await request.json()
    shopify_product_id = payload.get("id")

    if shopify_product_id is None:
        logger.warning(
            "Invalid products/update payload from %s: missing product id",
            store.shopify_domain,
        )
        return {"status": "ok", "result": "ignored_invalid_payload"}

    service = InventoryService(db=db, store=store)
    result = await service.update_product_from_webhook(payload)

    logger.info(
        "Webhook processed: topic=%s, product=%s, status=%s",
        topic,
        shopify_product_id,
        result.get("status"),
    )
    return {"status": "ok", "result": result}


# ═══════════════════════════════════════════════════════════════════
# POST /webhooks/app-uninstalled
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/app-uninstalled",
    summary="Handle app uninstallation from Shopify",
    description="Triggered when a merchant uninstalls the app. Marks the store as inactive.",
)
async def handle_app_uninstalled(
    request: Request,
    store: Store = Depends(_verify_and_get_store),
    db: AsyncSession = Depends(get_db),
):
    """
    Shopify webhook: `app/uninstalled`

    Payload:
        {
            "shop_id": 123456,
            "shop_domain": "my-store.myshopify.com",
            "shop_owner": "owner@email.com"
        }

    Flow:
        1. HMAC signature verified by _verify_and_get_store
        2. Call InventoryService.deactivate_store()
        3. Return 200 OK
    """
    topic = request.headers.get("x-shopify-topic", "unknown")
    logger.info(
        "Webhook received: topic=%s, shop=%s, id=%s",
        topic,
        store.shopify_domain,
        store.id,
    )

    service = InventoryService(db=db, store=store)
    result = await service.deactivate_store()

    logger.info(
        "Webhook processed: topic=%s, shop=%s, status=%s",
        topic,
        store.shopify_domain,
        result.get("status"),
    )
    return {"status": "ok", "result": result}
