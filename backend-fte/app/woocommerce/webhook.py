"""
WooCommerce Webhook Router.

Handles incoming webhook events from WooCommerce for real-time data synchronization.
All webhooks are routed through the WebhookManager for production-grade processing.

Supported webhook topics (path format replaces '.' with '/'):
- product/created, product/updated, product/deleted
- variation/created, variation/updated, variation/deleted
- order/created, order/updated, order/deleted
- customer/created, customer/updated, customer/deleted
- coupon/created, coupon/updated, coupon/deleted
- product/category/created, product/category/updated, product/category/deleted
- stock/updated
"""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.woocommerce.webhook_manager import WebhookManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/woocommerce/webhooks", tags=["WooCommerce Webhooks"])


@router.post("/{topic:path}", summary="Handle WooCommerce webhooks")
async def handle_webhook(
    request: Request,
    topic: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle all WooCommerce webhook topics via the WebhookManager.

    Converts FastAPI path format back to WooCommerce dot notation
    (e.g., "product/created" → "product.created") and delegates to
    WebhookManager.process_webhook() for full processing.

    Returns 200 OK in all cases to prevent WooCommerce from retrying
    webhooks that we intentionally reject (invalid signature, replay, etc.).
    Errors are logged and quarantined internally.
    """
    # Convert path format to WooCommerce topic dot notation
    wc_topic = topic.replace("/", ".")

    body = await request.body()
    headers = {
        "x-wc-webhook-source": request.headers.get("x-wc-webhook-source", ""),
        "x-wc-webhook-signature": request.headers.get("x-wc-webhook-signature", ""),
        "x-wc-webhook-id": request.headers.get("x-wc-webhook-id", ""),
        "x-wc-webhook-delivery-id": request.headers.get("x-wc-webhook-delivery-id", ""),
    }

    manager = WebhookManager(db=db)
    result = await manager.process_webhook(body, headers, wc_topic)

    logger.debug(
        "Webhook result: topic=%s, result=%s, detail=%s",
        wc_topic, result.get("result"), result.get("detail"),
    )

    return result
