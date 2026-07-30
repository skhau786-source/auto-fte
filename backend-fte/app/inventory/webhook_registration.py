"""
Webhook Registration Service.

Automatically registers Shopify webhooks after a store is connected
via OAuth. Called from the OAuth callback flow.

Topics registered for MVP:
- products/update
- inventory_levels/update
- app/uninstalled

Stores webhook IDs in the Store model for unregistration on uninstall.
"""

import logging
from typing import Optional

from app.inventory.shopify_client import ShopifyClient
from app.inventory.exceptions import ShopifySyncError

logger = logging.getLogger(__name__)

# ─── Webhook Topics for MVP ───

REQUIRED_WEBHOOKS = [
    {
        "topic": "products/update",
        "address": "/webhooks/products-update",
        "format": "json",
    },
    {
        "topic": "inventory_levels/update",
        "address": "/webhooks/inventory-levels-update",
        "format": "json",
    },
    {
        "topic": "app/uninstalled",
        "address": "/webhooks/app-uninstalled",
        "format": "json",
    },
]

# ─── Additional webhooks for post-MVP ───

OPTIONAL_WEBHOOKS = [
    {
        "topic": "products/create",
        "address": "/webhooks/products-update",
        "format": "json",
    },
    {
        "topic": "products/delete",
        "address": "/webhooks/products-delete",
        "format": "json",
    },
]


async def register_webhooks(
    shop_domain: str,
    access_token: str,
    app_base_url: str,
    api_version: Optional[str] = None,
) -> dict:
    """
    Register all required Shopify webhooks for a store.

    Called after OAuth completes successfully.

    Args:
        shop_domain: The store's myshopify.com domain.
        access_token: Shopify API access token.
        app_base_url: Public URL of the app (e.g., https://app.example.com).
        api_version: Shopify API version (default from settings).

    Returns:
        Dict mapping topic -> webhook_id for successfully registered webhooks.

    Raises:
        ShopifySyncError: If webhook registration fails entirely.
    """
    from app.config import settings

    base_url = app_base_url.rstrip("/")
    client = ShopifyClient(
        shop_domain=shop_domain,
        access_token=access_token,
        api_version=api_version or settings.SHOPIFY_API_VERSION,
    )

    results = {}

    try:
        for wh in REQUIRED_WEBHOOKS:
            topic = wh["topic"]
            address = f"{base_url}{wh['address']}"

            try:
                webhook_id = await _register_single_webhook(
                    client=client,
                    topic=topic,
                    address=address,
                    format=wh["format"],
                )
                results[topic] = webhook_id
                logger.info(
                    "Webhook registered: topic=%s, id=%s, address=%s",
                    topic,
                    webhook_id,
                    address,
                )
            except ShopifySyncError as exc:
                logger.error(
                    "Failed to register webhook %s for %s: %s",
                    topic,
                    shop_domain,
                    exc,
                )
                results[topic] = f"error: {exc}"

        return results

    finally:
        await client.close()


async def _register_single_webhook(
    client: ShopifyClient,
    topic: str,
    address: str,
    format: str = "json",
) -> int:
    """
    Register a single webhook via the Shopify REST API.

    POST /admin/api/{version}/webhooks.json

    Args:
        client: An initialized ShopifyClient.
        topic: Shopify webhook topic (e.g., "products/update").
        address: Full URL that Shopify will POST to.
        format: "json" (default).

    Returns:
        The Shopify webhook ID (integer).

    Raises:
        ShopifySyncError: If the API call fails.
    """
    path = "/webhooks.json"
    payload = {
        "webhook": {
            "topic": topic,
            "address": address,
            "format": format,
        }
    }

    data = await client._rest_post(path, payload)
    webhook = data.get("webhook", {})

    webhook_id = webhook.get("id")
    if webhook_id is None:
        raise ShopifySyncError(
            f"Webhook registration for '{topic}' returned no ID: {data}"
        )

    return webhook_id


async def unregister_webhook(
    shop_domain: str,
    access_token: str,
    webhook_id: int,
    api_version: Optional[str] = None,
) -> bool:
    """
    Delete a previously registered webhook.

    Called on app uninstall to clean up.

    DELETE /admin/api/{version}/webhooks/{id}.json

    Args:
        shop_domain: The store's myshopify.com domain.
        access_token: Shopify API access token.
        webhook_id: The Shopify webhook ID to delete.

    Returns:
        True if the webhook was deleted.
    """
    from app.config import settings

    client = ShopifyClient(
        shop_domain=shop_domain,
        access_token=access_token,
        api_version=api_version or settings.SHOPIFY_API_VERSION,
    )

    try:
        path = f"/webhooks/{webhook_id}.json"
        await client._rest_delete(path)
        logger.info(
            "Webhook unregistered: id=%d for %s",
            webhook_id,
            shop_domain,
        )
        return True
    except ShopifySyncError as exc:
        logger.warning(
            "Failed to unregister webhook %d for %s: %s",
            webhook_id,
            shop_domain,
            exc,
        )
        return False
    finally:
        await client.close()


async def get_existing_webhooks(
    shop_domain: str,
    access_token: str,
    api_version: Optional[str] = None,
) -> list[dict]:
    """
    List all registered webhooks for a store.

    Useful for verifying registration or finding orphaned webhooks.
    """
    from app.config import settings

    client = ShopifyClient(
        shop_domain=shop_domain,
        access_token=access_token,
        api_version=api_version or settings.SHOPIFY_API_VERSION,
    )

    try:
        data = await client._rest_get("/webhooks.json")
        return data.get("webhooks", [])
    finally:
        await client.close()
