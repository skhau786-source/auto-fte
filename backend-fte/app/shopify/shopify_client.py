"""
Shopify API Client for the Inventory Management module.

Single responsibility: communicate with the Shopify Admin API.
All Shopify-specific logic lives here — not in the service layer.

Supports:
- GraphQL product queries with cursor-based pagination
- REST inventory level adjustments
- Location fetching
- Rate-limit aware retry logic
- HMAC webhook signature verification
"""

import asyncio
import hmac
import hashlib
import logging
from typing import Optional, Any

import httpx

from app.config import settings
from app.inventory.exceptions import ShopifySyncError

logger = logging.getLogger(__name__)

# ─── Constants ───

DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 3
BASE_RETRY_DELAY_SECONDS = 1.0
PRODUCTS_PAGE_SIZE = 250
VARIANTS_PAGE_SIZE = 100

# HTTP status codes for retry
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


# ═══════════════════════════════════════════════════════════════════
# SHOPIFY CLIENT
# ═══════════════════════════════════════════════════════════════════


class ShopifyClient:
    """
    Asynchronous client for the Shopify Admin API.

    Usage:
        client = ShopifyClient(
            shop_domain="my-store.myshopify.com",
            access_token="shpat_abc123",
            location_id=123456,
        )
        products = await client.fetch_all_products()
    """

    def __init__(
        self,
        shop_domain: str,
        access_token: str,
        location_id: Optional[int] = None,
        api_version: Optional[str] = None,
    ):
        self.shop_domain = shop_domain
        self.access_token = access_token
        self.location_id = location_id
        self.api_version = api_version or settings.SHOPIFY_API_VERSION

        # Endpoints
        self.graphql_url = (
            f"https://{shop_domain}/admin/api/{self.api_version}/graphql.json"
        )
        self.rest_base = f"https://{shop_domain}/admin/api/{self.api_version}"

        # Headers
        self.headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "DigitalFTE-Inventory/1.0",
        }

        # HTTP client config
        self.timeout = httpx.Timeout(DEFAULT_TIMEOUT_SECONDS)
        self.max_retries = MAX_RETRIES

        # Async HTTP client (lazy-initialized per request)
        self._client: Optional[httpx.AsyncClient] = None

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Products
    # ═══════════════════════════════════════════════════════════════

    async def fetch_all_products(self) -> list[dict]:
        """
        Fetch ALL products (with variants) from Shopify using GraphQL.

        Uses cursor-based pagination to traverse all pages.
        Returns a flat list of normalized product dicts with embedded variant dicts.

        Each product dict contains:
            id, title, body_html, vendor, product_type, status,
            featured_image_url, variants (list)
        """
        query = """
        query Products($cursor: String) {
            products(first: %d, after: $cursor) {
                edges {
                    node {
                        id
                        title
                        bodyHtml
                        vendor
                        productType
                        status
                        featuredImage { url }
                        variants(first: %d) {
                            edges {
                                node {
                                    id
                                    title
                                    sku
                                    barcode
                                    price
                                    compareAtPrice
                                    inventoryQuantity
                                    requiresShipping
                                    inventoryItem { id }
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
        """ % (PRODUCTS_PAGE_SIZE, VARIANTS_PAGE_SIZE)

        raw_products = await self._paginate_graphql("products", query)
        return [self._normalize_product(p) for p in raw_products]

    async def fetch_products_page(
        self, cursor: Optional[str] = None
    ) -> tuple[list[dict], Optional[str]]:
        """
        Fetch a single page of products from Shopify.

        Returns (normalized_products, next_cursor).
        next_cursor is None when there are no more pages.
        Useful for streaming / background sync without loading everything into memory.
        """
        query = """
        query Products($cursor: String) {
            products(first: %d, after: $cursor) {
                edges {
                    node {
                        id
                        title
                        bodyHtml
                        vendor
                        productType
                        status
                        featuredImage { url }
                        variants(first: %d) {
                            edges {
                                node {
                                    id
                                    title
                                    sku
                                    barcode
                                    price
                                    compareAtPrice
                                    inventoryQuantity
                                    requiresShipping
                                    inventoryItem { id }
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
        """ % (PRODUCTS_PAGE_SIZE, VARIANTS_PAGE_SIZE)

        data = await self._graphql(query, {"cursor": cursor})
        products_data = data.get("products", {})
        edges = products_data.get("edges", [])
        page_info = products_data.get("pageInfo", {})

        products = [self._normalize_product(e["node"]) for e in edges]
        next_cursor = page_info.get("endCursor") if page_info.get("hasNextPage") else None

        return products, next_cursor

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Variants
    # ═══════════════════════════════════════════════════════════════

    async def fetch_variants(self, product_id: int) -> list[dict]:
        """
        Fetch all variants for a single product by its Shopify numeric ID.

        Used when refreshing a single product (e.g., after a products/update webhook)
        without needing to re-fetch all products.
        """
        query = """
        query ProductVariants($id: ID!) {
            product(id: $id) {
                variants(first: %d) {
                    edges {
                        node {
                            id
                            title
                            sku
                            barcode
                            price
                            compareAtPrice
                            inventoryQuantity
                            requiresShipping
                            inventoryItem { id }
                        }
                    }
                }
            }
        }
        """ % (VARIANTS_PAGE_SIZE)

        data = await self._graphql(query, {"id": self._to_gid("Product", product_id)})
        product_data = data.get("product", {})
        edges = product_data.get("variants", {}).get("edges", [])

        variants = []
        for ve in edges:
            v = ve["node"]
            variants.append({
                "id": self._gid_to_id(v["id"]),
                "title": v.get("title", ""),
                "sku": v.get("sku"),
                "barcode": v.get("barcode"),
                "price": v.get("price", "0.00"),
                "compare_at_price": v.get("compareAtPrice"),
                "inventory_quantity": v.get("inventoryQuantity", 0),
                "requires_shipping": v.get("requiresShipping", True),
                "inventory_item_id": self._gid_to_id(
                    v.get("inventoryItem", {}).get("id", "0")
                ),
            })

        return variants

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Inventory Levels
    # ═══════════════════════════════════════════════════════════════

    async def fetch_inventory_level(
        self,
        inventory_item_id: int,
        location_id: int,
    ) -> Optional[int]:
        """
        Fetch the current available quantity for an inventory item at a location.

        Uses the GraphQL `inventoryLevel` query.
        Returns the available count, or None if the item is not tracked at this location.
        """
        query = """
        query InventoryLevel($inventoryItemId: ID!, $locationId: ID!) {
            inventoryLevel(inventoryItemId: $inventoryItemId, locationId: $locationId) {
                available
            }
        }
        """
        variables = {
            "inventoryItemId": self._to_gid("InventoryItem", inventory_item_id),
            "locationId": self._to_gid("Location", location_id),
        }

        data = await self._graphql(query, variables)
        level = data.get("inventoryLevel", {})
        if level is None:
            return None
        return level.get("available")

    async def set_inventory_level(
        self,
        inventory_item_id: int,
        location_id: int,
        quantity: int,
    ) -> dict:
        """
        Set the absolute inventory quantity for an item at a location.

        Uses the `inventorySetQuantity` GraphQL mutation.
        This is the PRIMARY method for setting inventory.
        """
        mutation = """
        mutation InventorySet($input: InventorySetQuantityInput!) {
            inventorySetQuantity(input: $input) {
                inventoryLevel {
                    id
                    available
                }
                userErrors { field message }
            }
        }
        """
        variables = {
            "input": {
                "inventoryItemId": self._to_gid("InventoryItem", inventory_item_id),
                "locationId": self._to_gid("Location", location_id),
                "quantity": quantity,
            }
        }

        result = await self._graphql(mutation, variables)
        level_data = result.get("inventorySetQuantity", {})

        # Check for user errors
        user_errors = level_data.get("userErrors", [])
        if user_errors:
            error_messages = "; ".join(
                f"{e.get('field', 'unknown')}: {e.get('message', 'unknown')}"
                for e in user_errors
            )
            raise ShopifySyncError(f"Inventory set failed: {error_messages}")

        return level_data.get("inventoryLevel", {})

    async def adjust_inventory_level(
        self,
        inventory_item_id: int,
        location_id: int,
        available_adjustment: int,
    ) -> dict:
        """
        Adjust inventory by a delta (positive or negative).

        Uses the REST endpoint:
        POST /admin/api/{version}/inventory_levels/adjust.json

        This is useful when you only know the change amount, not the target quantity.
        If the REST adjust fails, it falls back to:
        1. Fetching the current level via GraphQL
        2. Computing the target quantity
        3. Calling set_inventory_level (GraphQL mutation)

        Note: The GraphQL inventorySetQuantity is preferred when the target quantity is known.
        """
        path = "/inventory_levels/adjust.json"
        payload = {
            "location_id": location_id,
            "inventory_item_id": inventory_item_id,
            "available_adjustment": available_adjustment,
        }

        try:
            data = await self._rest_post(path, payload)
            return data.get("inventory_level", {})
        except ShopifySyncError as exc:
            logger.warning(
                "REST adjust failed for item %s: %s. Falling back to GraphQL set.",
                inventory_item_id,
                exc,
            )
            # Fall back: fetch current level, compute target, set via GraphQL
            current = await self.fetch_inventory_level(inventory_item_id, location_id)
            if current is not None:
                target = current + available_adjustment
                if target < 0:
                    raise ShopifySyncError(
                        f"Adjustment would set inventory below zero for item {inventory_item_id}: "
                        f"current={current}, adjustment={available_adjustment}"
                    )
                result = await self.set_inventory_level(
                    inventory_item_id, location_id, target
                )
                logger.info(
                    "Fallback succeeded for item %s: adjusted from %d to %d",
                    inventory_item_id,
                    current,
                    target,
                )
                return result
            # Fallback failed — current level was None
            raise

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Locations
    # ═══════════════════════════════════════════════════════════════

    async def fetch_locations(self) -> list[dict]:
        """
        Fetch all locations for the store.

        GET /admin/api/{version}/locations.json
        Returns a list of location dicts with id, name, address, etc.
        """
        path = "/locations.json"
        data = await self._rest_get(path)
        return data.get("locations", [])

    async def get_primary_location_id(self) -> Optional[int]:
        """
        Get the ID of the primary (default) location.
        Returns None if no locations exist.

        This is used to populate store.shopify_location_id during setup.
        """
        locations = await self.fetch_locations()
        if not locations:
            return None

        # Shopify marks the primary location with a `primary` field or it's the first one
        for loc in locations:
            if loc.get("primary") or loc.get("is_primary"):
                return self._gid_to_id(loc["id"]) if "gid" in str(loc.get("id")) else loc["id"]

        # Fall back to the first location
        first = locations[0]
        return self._gid_to_id(first["id"]) if "gid" in str(first.get("id")) else first["id"]

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Webhook Verification (Static)
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def verify_webhook(hmac_header: str, body: bytes, client_secret: str) -> bool:
        """
        Verify that a webhook request came from Shopify.

        Args:
            hmac_header: Value of the X-Shopify-Hmac-Sha256 header.
            body: Raw request body (bytes).
            client_secret: Shopify app client secret (from settings).

        Returns:
            True if the signature is valid, False otherwise.

        Usage:
            is_valid = ShopifyClient.verify_webhook(
                hmac_header=request.headers["x-shopify-hmac-sha256"],
                body=await request.body(),
                client_secret=settings.SHOPIFY_API_SECRET,
            )
        """
        computed_digest = hmac.new(
            client_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(computed_digest, hmac_header)

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL — HTTP Helpers
    # ═══════════════════════════════════════════════════════════════

    async def _graphql(self, query: str, variables: Optional[dict] = None) -> dict:
        """Execute a GraphQL query/mutation and return the data dict."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        data = await self._request("POST", self.graphql_url, json=payload)

        if "errors" in data:
            error_msg = data["errors"][0].get("message", str(data["errors"]))
            raise ShopifySyncError(f"GraphQL error: {error_msg}")

        return data.get("data", {})

    async def _rest_get(self, path: str) -> dict:
        """Execute a REST GET request."""
        url = f"{self.rest_base}{path}"
        return await self._request("GET", url)

    async def _rest_post(self, path: str, json_payload: dict) -> dict:
        """Execute a REST POST request."""
        url = f"{self.rest_base}{path}"
        return await self._request("POST", url, json=json_payload)

    async def _rest_delete(self, path: str) -> dict:
        """Execute a REST DELETE request."""
        url = f"{self.rest_base}{path}"
        return await self._request("DELETE", url)

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> dict:
        """
        Core HTTP request method with retry logic.

        Retries on:
        - 429 Too Many Requests (respects Retry-After header)
        - 5xx Server Errors
        - Network timeouts / connection errors

        Does NOT retry on 4xx Client Errors (except 429).
        """
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                client = self._get_client()
                response = await client.request(
                    method,
                    url,
                    headers=self.headers,
                    timeout=self.timeout,
                    **kwargs,
                )

                # Success
                if response.is_success:
                    return response.json()

                # Rate limited — respect Retry-After
                if response.status_code == 429:
                    retry_after = self._parse_retry_after(response)
                    logger.warning(
                        "Shopify rate limited (429). Retrying in %ds (attempt %d/%d)",
                        retry_after,
                        attempt,
                        self.max_retries,
                    )
                    await asyncio.sleep(retry_after)
                    continue

                # Retryable server error
                if response.status_code in RETRYABLE_STATUSES:
                    delay = BASE_RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                    logger.warning(
                        "Shopify server error %d. Retrying in %.1fs (attempt %d/%d)",
                        response.status_code,
                        delay,
                        attempt,
                        self.max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable client error
                error_body = response.text[:500]
                raise ShopifySyncError(
                    f"Shopify API error {response.status_code}: {error_body}"
                )

            except httpx.TimeoutException as exc:
                last_exception = exc
                delay = BASE_RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "Shopify request timeout. Retrying in %.1fs (attempt %d/%d)",
                    delay,
                    attempt,
                    self.max_retries,
                )
                await asyncio.sleep(delay)

            except httpx.NetworkError as exc:
                last_exception = exc
                delay = BASE_RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "Shopify network error: %s. Retrying in %.1fs (attempt %d/%d)",
                    exc,
                    delay,
                    attempt,
                    self.max_retries,
                )
                await asyncio.sleep(delay)

        # All retries exhausted
        error_msg = str(last_exception) if last_exception else "Max retries exceeded"
        raise ShopifySyncError(f"Shopify request failed after {self.max_retries} retries: {error_msg}")

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL — Pagination
    # ═══════════════════════════════════════════════════════════════

    async def _paginate_graphql(self, resource: str, query_template: str) -> list[dict]:
        """
        Walk through all pages of a GraphQL connection using cursor-based pagination.

        Args:
            resource: The top-level field name in the response (e.g., "products").
            query_template: GraphQL query with a $cursor variable.

        Returns:
            A flat list of all items across all pages.
        """
        all_items: list[dict] = []
        cursor: Optional[str] = None
        has_next = True

        while has_next:
            data = await self._graphql(query_template, {"cursor": cursor})
            page_data = data.get(resource, {})
            edges = page_data.get("edges", [])
            page_info = page_data.get("pageInfo", {})

            for edge in edges:
                all_items.append(edge["node"])

            has_next = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")

        return all_items

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL — Helpers
    # ═══════════════════════════════════════════════════════════════

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared httpx AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient()
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    @staticmethod
    def _normalize_product(raw: dict) -> dict:
        """
        Convert a raw GraphQL product node into the format expected by
        ProductRepository.upsert_from_shopify.

        Transforms:
        - GID strings → integer IDs
        - Nested variant edges → flat variant list
        - featuredImage nested object → featured_image_url string
        """
        variants_raw = raw.get("variants", {}).get("edges", [])
        variants = []
        for ve in variants_raw:
            v = ve["node"]
            variants.append({
                "id": ShopifyClient._gid_to_id(v["id"]),
                "title": v.get("title", ""),
                "sku": v.get("sku"),
                "barcode": v.get("barcode"),
                "price": v.get("price", "0.00"),
                "compare_at_price": v.get("compareAtPrice"),
                "inventory_quantity": v.get("inventoryQuantity", 0),
                "requires_shipping": v.get("requiresShipping", True),
                "inventory_item_id": ShopifyClient._gid_to_id(
                    v.get("inventoryItem", {}).get("id", "0")
                ),
            })

        featured_image = raw.get("featuredImage") or {}
        return {
            "id": ShopifyClient._gid_to_id(raw["id"]),
            "title": raw.get("title", ""),
            "body_html": raw.get("bodyHtml"),
            "vendor": raw.get("vendor"),
            "product_type": raw.get("productType"),
            "status": raw.get("status", "active"),
            "featured_image_url": featured_image.get("url"),
            "variants": variants,
        }

    @staticmethod
    def _gid_to_id(gid: str) -> int:
        """
        Convert a Shopify GID to a numeric ID.

        Examples:
            "gid://shopify/Product/123456" → 123456
            "gid://shopify/InventoryItem/789" → 789
        """
        try:
            return int(gid.split("/")[-1])
        except (ValueError, IndexError, AttributeError):
            logger.warning("Failed to parse GID: %s", gid)
            return 0

    @staticmethod
    def _to_gid(resource: str, resource_id: int) -> str:
        """
        Convert a numeric ID to a Shopify GID.

        Example:
            ("InventoryItem", 123456) → "gid://shopify/InventoryItem/123456"
        """
        return f"gid://shopify/{resource}/{resource_id}"

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> int:
        """Parse the Retry-After header from a rate-limited response."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return int(retry_after)
            except (ValueError, TypeError):
                pass
        return 2  # Default retry delay for rate limits
