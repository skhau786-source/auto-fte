# ═══════════════════════════════════════════════════════════════
# agents / customer_support / shopify_storefront_client.py
#
# PURPOSE: Shopify Storefront API client for cart operations.
#          No mock/dev mode: every call is a real request, and anything
#          short of a verified success raises StorefrontError so callers
#          can never show a fake checkout link.
# ═══════════════════════════════════════════════════════════════

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}$")


class StorefrontError(Exception):
    """Shopify rejected the request, was unreachable, or returned an unusable response."""


class StorefrontNotConfigured(StorefrontError):
    """Shop domain or Storefront access token is missing/invalid, so no request was made."""


class ShopifyStorefrontClient:
    """Client for Shopify Storefront API (Cart operations)."""

    def __init__(
        self,
        shop_domain: str = "",
        access_token: str = "",
        api_url: str = "https://{shop}/api/2024-01/graphql.json",
        http_client: Optional[httpx.AsyncClient] = None,
        timeout: float = 15.0,
    ):
        self.shop_domain = (shop_domain or "").strip().lower()
        self.access_token = (access_token or "").strip()
        self.api_url = api_url.format(shop=self.shop_domain)
        self._http_client = http_client
        self._timeout = timeout

    # ─── internals ──────────────────────────────────────────────

    def _require_config(self) -> None:
        if not self.access_token:
            raise StorefrontNotConfigured("Storefront access token is not configured")
        if not self.shop_domain or not _DOMAIN_RE.match(self.shop_domain):
            raise StorefrontNotConfigured("Store has no valid shop domain")

    async def _graphql(self, query: str, variables: dict) -> dict:
        """POST a GraphQL document; return its `data`. Raises StorefrontError on any failure."""
        self._require_config()
        headers = {
            "X-Shopify-Storefront-Access-Token": self.access_token,
            "Content-Type": "application/json",
        }
        try:
            if self._http_client is not None:
                res = await self._http_client.post(
                    self.api_url, json={"query": query, "variables": variables}, headers=headers
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    res = await client.post(
                        self.api_url, json={"query": query, "variables": variables}, headers=headers
                    )
        except httpx.HTTPError as e:
            raise StorefrontError(f"Could not reach Shopify: {type(e).__name__}") from e

        if res.status_code in (401, 403):
            raise StorefrontError(f"Shopify rejected the Storefront token (HTTP {res.status_code})")
        if res.status_code != 200:
            raise StorefrontError(f"Shopify returned HTTP {res.status_code}")
        try:
            payload = res.json()
        except ValueError as e:
            raise StorefrontError("Shopify returned a non-JSON response") from e

        if payload.get("errors"):
            raise StorefrontError(f"Shopify GraphQL error: {_short(payload['errors'])}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise StorefrontError("Shopify response had no data")
        return data

    @staticmethod
    def _raise_on_user_errors(result: dict) -> None:
        user_errors = result.get("userErrors") or []
        if user_errors:
            raise StorefrontError(f"Shopify refused the cart: {_short(user_errors)}")

    # ─── public API ─────────────────────────────────────────────

    async def create_cart(self, lines: list[dict]) -> dict:
        """Create a cart with the given lines ({"merchandiseId", "quantity"}).

        Returns {"cart_id", "checkout_url", "total_quantity"} straight from Shopify's response.
        """
        mutation = """
        mutation cartCreate($input: CartInput) {
          cartCreate(input: $input) {
            cart {
              id
              checkoutUrl
              totalQuantity
            }
            userErrors { field message }
          }
        }
        """
        data = await self._graphql(mutation, {"input": {"lines": lines}})
        result = data.get("cartCreate") or {}
        self._raise_on_user_errors(result)
        cart = result.get("cart") or {}
        if not cart.get("id") or not cart.get("checkoutUrl"):
            raise StorefrontError("Shopify did not return a cart with a checkout URL")
        return {
            "cart_id": cart["id"],
            "checkout_url": cart["checkoutUrl"],
            "total_quantity": cart.get("totalQuantity"),
        }

    async def cart_lines_add(self, cart_id: str, lines: list[dict]) -> dict:
        """Add lines to an existing cart. Returns {"cart_id", "checkout_url", "total_quantity"}."""
        mutation = """
        mutation cartLinesAdd($cartId: ID!, $lines: [CartLineInput!]!) {
          cartLinesAdd(cartId: $cartId, lines: $lines) {
            cart { id checkoutUrl totalQuantity }
            userErrors { field message }
          }
        }
        """
        data = await self._graphql(mutation, {"cartId": cart_id, "lines": lines})
        result = data.get("cartLinesAdd") or {}
        self._raise_on_user_errors(result)
        cart = result.get("cart") or {}
        if not cart.get("id") or not cart.get("checkoutUrl"):
            raise StorefrontError("Shopify did not return the updated cart")
        return {
            "cart_id": cart["id"],
            "checkout_url": cart["checkoutUrl"],
            "total_quantity": cart.get("totalQuantity"),
        }


def _short(obj, limit: int = 300) -> str:
    text = str(obj)
    return text if len(text) <= limit else text[:limit] + "…"
