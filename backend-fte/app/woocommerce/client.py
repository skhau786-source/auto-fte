"""
WooCommerce REST API Client.

Asynchronous HTTP client for the WooCommerce REST API (v3).
Handles authentication, pagination, rate limiting, retry logic,
and data normalization.

Uses Consumer Key / Consumer Secret (Basic Auth or OAuth1.0a).
"""

import asyncio
import logging
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from httpx import BasicAuth

from app.config import settings
from app.woocommerce.constants import (
    WC_API_VERSION,
    REQUEST_TIMEOUT_SECONDS,
    PRODUCTS_PER_PAGE,
    ORDERS_PER_PAGE,
    CUSTOMERS_PER_PAGE,
    MAX_RETRY_ATTEMPTS,
)
from app.woocommerce.exceptions import (
    WooCommerceAPIError,
    WooCommerceRateLimitError,
    StoreConnectionError,
    ProductNotFoundError,
    OrderNotFoundError,
    CustomerNotFoundError,
    CategoryNotFoundError,
    CouponNotFoundError,
)

logger = logging.getLogger(__name__)

# HTTP status codes eligible for retry
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
BASE_RETRY_DELAY = 1.0

# Map HTTP status codes to specific exception types for precise error handling
HTTP_STATUS_ERROR_MAP: dict[int, type[WooCommerceAPIError]] = {
    400: WooCommerceAPIError,  # Bad Request
    404: ProductNotFoundError,  # Not Found (ambiguous, caught generically)
    409: WooCommerceAPIError,  # Conflict
    410: WooCommerceAPIError,  # Gone
}

# Resource-specific 404 mapping
RESOURCE_404_MAP: dict[str, type[WooCommerceAPIError]] = {
    "products": ProductNotFoundError,
    "orders": OrderNotFoundError,
    "customers": CustomerNotFoundError,
    "categories": CategoryNotFoundError,
    "coupons": CouponNotFoundError,
}


class WooCommerceClient:
    """
    Async HTTP client for the WooCommerce REST API.

    Usage:
        client = WooCommerceClient(
            store_url="https://example.com",
            consumer_key="ck_xxxxx",
            consumer_secret="cs_xxxxx",
        )
        products = await client.get_products(page=1, per_page=50)
        await client.close()
    """

    def __init__(
        self,
        store_url: str,
        consumer_key: str,
        consumer_secret: str,
        api_version: str = WC_API_VERSION,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ):
        # Normalize URL (strip trailing slash)
        self.store_url = store_url.rstrip("/")
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.api_version = api_version
        self.timeout = timeout

        # Build base API URL
        self.api_base = f"{self.store_url}/wp-json/{api_version}"

        # Authentication
        self.auth = BasicAuth(username=consumer_key, password=consumer_secret)

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None

        self.logger = logging.getLogger(f"{__name__}.WooCommerceClient")

        # Request tracking for metrics
        self._request_count: int = 0
        self._error_count: int = 0

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Connection Verification
    # ═══════════════════════════════════════════════════════════════

    async def verify_connection(self) -> dict:
        """
        Verify that the WooCommerce API credentials are valid.

        Fetches the system status to confirm connectivity.
        Returns store info on success, raises StoreConnectionError on failure.
        """
        try:
            data = await self._get("/")
            return {
                "status": "connected",
                "api_version": self.api_version,
                "store_url": self.store_url,
                "woocommerce_version": data.get("store", {}).get("wc_version", "unknown"),
            }
        except Exception as exc:
            raise StoreConnectionError(str(exc))

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Products
    # ═══════════════════════════════════════════════════════════════

    async def get_products(
        self,
        page: int = 1,
        per_page: int = PRODUCTS_PER_PAGE,
        after: Optional[str] = None,
        before: Optional[str] = None,
        status: Optional[str] = None,
        sku: Optional[str] = None,
        category: Optional[int] = None,
        tag: Optional[int] = None,
        search: Optional[str] = None,
        orderby: str = "date",
        order: str = "desc",
    ) -> tuple[list[dict], dict]:
        """
        Fetch paginated products from WooCommerce.

        Returns:
            Tuple of (products_list, headers_dict) where headers contain
            X-WP-Total and X-WP-TotalPages for pagination metadata.
        """
        params = {
            "page": page,
            "per_page": per_page,
            "orderby": orderby,
            "order": order,
        }
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if status:
            params["status"] = status
        if sku:
            params["sku"] = sku
        if category:
            params["category"] = category
        if tag:
            params["tag"] = tag
        if search:
            params["search"] = search

        return await self._get_paginated("/products", params)

    async def get_product(self, product_id: int) -> dict:
        """Fetch a single product by ID."""
        return await self._get(f"/products/{product_id}")

    async def get_product_by_sku(self, sku: str) -> Optional[dict]:
        """Fetch a product by SKU."""
        products, _ = await self.get_products(sku=sku, per_page=1)
        return products[0] if products else None

    async def create_product(self, product_data: dict) -> dict:
        """Create a new product in WooCommerce."""
        return await self._post("/products", product_data)

    async def update_product(self, product_id: int, product_data: dict) -> dict:
        """Update an existing product in WooCommerce."""
        return await self._put(f"/products/{product_id}", product_data)

    async def delete_product(self, product_id: int, force: bool = True) -> dict:
        """Delete a product from WooCommerce."""
        return await self._delete(f"/products/{product_id}", params={"force": force})

    async def get_all_products(
        self,
        after: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch ALL products from WooCommerce using automatic pagination.
        Useful for initial full sync.
        """
        return await self._paginate_all("/products", {
            "after": after,
            "status": status,
            "orderby": "date",
            "order": "asc",
        })

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Product Variations
    # ═══════════════════════════════════════════════════════════════

    async def get_variations(
        self,
        product_id: int,
        page: int = 1,
        per_page: int = PRODUCTS_PER_PAGE,
    ) -> tuple[list[dict], dict]:
        """
        Fetch paginated variations for a variable product.

        Args:
            product_id: WooCommerce product ID
            page: Page number (1-indexed)
            per_page: Items per page

        Returns:
            Tuple of (variations_list, headers_dict)
        """
        params = {"page": page, "per_page": per_page}
        return await self._get_paginated(f"/products/{product_id}/variations", params)

    async def get_all_variations(self, product_id: int) -> list[dict]:
        """Fetch ALL variations for a product using automatic pagination."""
        return await self._paginate_all(
            f"/products/{product_id}/variations",
            {"per_page": PRODUCTS_PER_PAGE},
        )

    async def get_variation(self, product_id: int, variation_id: int) -> dict:
        """Fetch a single variation by ID."""
        return await self._get(f"/products/{product_id}/variations/{variation_id}")

    async def update_variation(self, product_id: int, variation_id: int, data: dict) -> dict:
        """Update a specific variation (e.g., price, stock)."""
        return await self._put(f"/products/{product_id}/variations/{variation_id}", data)

    async def create_variation(self, product_id: int, data: dict) -> dict:
        """Create a new variation for a variable product."""
        return await self._post(f"/products/{product_id}/variations", data)

    async def delete_variation(self, product_id: int, variation_id: int, force: bool = True) -> dict:
        """Delete a variation from WooCommerce."""
        return await self._delete(
            f"/products/{product_id}/variations/{variation_id}",
            params={"force": force},
        )

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Categories
    # ═══════════════════════════════════════════════════════════════

    async def get_categories(
        self,
        page: int = 1,
        per_page: int = PRODUCTS_PER_PAGE,
        parent: Optional[int] = None,
        search: Optional[str] = None,
        orderby: str = "name",
        order: str = "asc",
    ) -> tuple[list[dict], dict]:
        """Fetch paginated product categories."""
        params = {
            "page": page,
            "per_page": per_page,
            "orderby": orderby,
            "order": order,
        }
        if parent is not None:
            params["parent"] = parent
        if search:
            params["search"] = search
        return await self._get_paginated("/products/categories", params)

    async def get_all_categories(self) -> list[dict]:
        """Fetch ALL categories using automatic pagination."""
        return await self._paginate_all("/products/categories", {"orderby": "name", "order": "asc", "per_page": PRODUCTS_PER_PAGE})

    async def get_category(self, category_id: int) -> dict:
        """Fetch a single category by ID."""
        return await self._get(f"/products/categories/{category_id}")

    async def create_category(self, category_data: dict) -> dict:
        """Create a new category."""
        return await self._post("/products/categories", category_data)

    async def update_category(self, category_id: int, category_data: dict) -> dict:
        """Update an existing category."""
        return await self._put(f"/products/categories/{category_id}", category_data)

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Orders
    # ═══════════════════════════════════════════════════════════════

    async def get_orders(
        self,
        page: int = 1,
        per_page: int = ORDERS_PER_PAGE,
        after: Optional[str] = None,
        before: Optional[str] = None,
        status: Optional[str] = None,
        customer: Optional[int] = None,
        search: Optional[str] = None,
        orderby: str = "date",
        order: str = "desc",
    ) -> tuple[list[dict], dict]:
        """Fetch paginated orders."""
        params = {
            "page": page,
            "per_page": per_page,
            "orderby": orderby,
            "order": order,
        }
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if status:
            params["status"] = status
        if customer:
            params["customer"] = customer
        if search:
            params["search"] = search
        return await self._get_paginated("/orders", params)

    async def get_all_orders(
        self,
        after: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        """Fetch ALL orders using automatic pagination."""
        return await self._paginate_all("/orders", {
            "after": after,
            "status": status,
            "orderby": "date",
            "order": "asc",
        })

    async def get_order(self, order_id: int) -> dict:
        """Fetch a single order by ID."""
        return await self._get(f"/orders/{order_id}")

    async def update_order(self, order_id: int, order_data: dict) -> dict:
        """Update an existing order (e.g., status change)."""
        return await self._put(f"/orders/{order_id}", order_data)

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Customers
    # ═══════════════════════════════════════════════════════════════

    async def get_customers(
        self,
        page: int = 1,
        per_page: int = CUSTOMERS_PER_PAGE,
        email: Optional[str] = None,
        role: Optional[str] = None,
        search: Optional[str] = None,
        orderby: str = "registered_date",
        order: str = "desc",
    ) -> tuple[list[dict], dict]:
        """Fetch paginated customers."""
        params = {
            "page": page,
            "per_page": per_page,
            "orderby": orderby,
            "order": order,
        }
        if email:
            params["email"] = email
        if role:
            params["role"] = role
        if search:
            params["search"] = search
        return await self._get_paginated("/customers", params)

    async def get_all_customers(self) -> list[dict]:
        """Fetch ALL customers using automatic pagination."""
        return await self._paginate_all("/customers", {"per_page": CUSTOMERS_PER_PAGE, "orderby": "registered_date", "order": "asc"})

    async def get_customer(self, customer_id: int) -> dict:
        """Fetch a single customer by ID."""
        return await self._get(f"/customers/{customer_id}")

    async def create_customer(self, customer_data: dict) -> dict:
        """Create a new customer."""
        return await self._post("/customers", customer_data)

    async def update_customer(self, customer_id: int, customer_data: dict) -> dict:
        """Update an existing customer."""
        return await self._put(f"/customers/{customer_id}", customer_data)

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Inventory / Stock
    # ═══════════════════════════════════════════════════════════════

    async def update_stock(
        self,
        product_id: int,
        stock_quantity: int,
        stock_status: Optional[str] = None,
    ) -> dict:
        """
        Update stock quantity for a single product.

        Args:
            product_id: WooCommerce product ID
            stock_quantity: New stock quantity
            stock_status: Optional stock status ("instock", "outofstock", "onbackorder")

        Returns:
            Updated product data from WooCommerce
        """
        data: dict[str, Any] = {
            "stock_quantity": stock_quantity,
            "manage_stock": True,
        }
        if stock_status:
            data["stock_status"] = stock_status
        else:
            data["stock_status"] = "instock" if stock_quantity > 0 else "outofstock"

        self.logger.info(
            "Updating stock for product %d: quantity=%d, status=%s",
            product_id, stock_quantity, data["stock_status"],
        )
        return await self.update_product(product_id, data)

    async def batch_update_stock(self, items: list[dict]) -> list[dict]:
        """
        Batch update stock for multiple products.

        Each item should contain:
        - product_id (int): WooCommerce product ID
        - stock_quantity (int): New stock quantity
        - stock_status (str, optional): Stock status

        Args:
            items: List of stock update dicts

        Returns:
            List of WooCommerce responses (successes + failures)
        """
        results: list[dict] = []
        for item in items:
            try:
                result = await self.update_stock(
                    product_id=item["product_id"],
                    stock_quantity=item["stock_quantity"],
                    stock_status=item.get("stock_status"),
                )
                results.append({
                    "product_id": item["product_id"],
                    "status": "updated",
                    "stock_quantity": item["stock_quantity"],
                    "data": result,
                })
            except Exception as exc:
                self.logger.error(
                    "Batch stock update failed for product %d: %s",
                    item["product_id"], exc,
                )
                results.append({
                    "product_id": item["product_id"],
                    "status": "failed",
                    "error": str(exc),
                })
        return results

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Coupons
    # ═══════════════════════════════════════════════════════════════

    async def get_coupons(
        self,
        page: int = 1,
        per_page: int = PRODUCTS_PER_PAGE,
        search: Optional[str] = None,
        orderby: str = "date",
        order: str = "desc",
    ) -> tuple[list[dict], dict]:
        """Fetch paginated coupons."""
        params = {
            "page": page,
            "per_page": per_page,
            "orderby": orderby,
            "order": order,
        }
        if search:
            params["search"] = search
        return await self._get_paginated("/coupons", params)

    async def get_all_coupons(self) -> list[dict]:
        """Fetch ALL coupons using automatic pagination."""
        return await self._paginate_all("/coupons", {"per_page": PRODUCTS_PER_PAGE, "orderby": "date", "order": "asc"})

    async def get_coupon(self, coupon_id: int) -> dict:
        """Fetch a single coupon by ID."""
        return await self._get(f"/coupons/{coupon_id}")

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Webhooks
    # ═══════════════════════════════════════════════════════════════

    async def get_webhooks(
        self,
        page: int = 1,
        per_page: int = PRODUCTS_PER_PAGE,
    ) -> tuple[list[dict], dict]:
        """Fetch paginated webhooks."""
        params = {"page": page, "per_page": per_page}
        return await self._get_paginated("/webhooks", params)

    async def create_webhook(self, webhook_data: dict) -> dict:
        """Register a new webhook in WooCommerce."""
        return await self._post("/webhooks", webhook_data)

    async def delete_webhook(self, webhook_id: int) -> dict:
        """Delete a webhook from WooCommerce."""
        return await self._delete(f"/webhooks/{webhook_id}", params={"force": True})

    async def register_required_webhooks(self, callback_url: str) -> list[dict]:
        """
        Register all required webhooks for real-time sync.
        Returns a list of created webhook responses.

        Required webhook topics:
        - product.created, product.updated, product.deleted
        - order.created, order.updated, order.deleted
        - customer.created, customer.updated, customer.deleted
        - coupon.created, coupon.updated, coupon.deleted
        - category.created, category.updated, category.deleted
        """
        topics = [
            "product.created", "product.updated", "product.deleted",
            "order.created", "order.updated", "order.deleted",
            "customer.created", "customer.updated", "customer.deleted",
            "coupon.created", "coupon.updated", "coupon.deleted",
            "product.category.created", "product.category.updated", "product.category.deleted",
        ]

        results = []
        for topic in topics:
            try:
                webhook = await self.create_webhook({
                    "name": f"Digital FTE - {topic}",
                    "topic": topic,
                    "delivery_url": f"{callback_url}/api/woocommerce/webhooks/{topic.replace('.', '/')}",
                    "secret": settings.WOOCOMMERCE_WEBHOOK_SECRET or "",
                })
                results.append({"topic": topic, "id": webhook.get("id"), "status": "created"})
                logger.info("Registered webhook: %s (ID: %s)", topic, webhook.get("id"))
            except Exception as exc:
                logger.error("Failed to register webhook %s: %s", topic, exc)
                results.append({"topic": topic, "status": "failed", "error": str(exc)})

        return results

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Reports
    # ═══════════════════════════════════════════════════════════════

    async def get_sales_report(
        self,
        period: str = "month",
        date_min: Optional[str] = None,
        date_max: Optional[str] = None,
    ) -> list[dict]:
        """Fetch sales report data."""
        params = {"period": period}
        if date_min:
            params["date_min"] = date_min
        if date_max:
            params["date_max"] = date_max
        return await self._get("/reports/sales", params=params)

    async def get_top_sellers(
        self,
        period: str = "month",
        date_min: Optional[str] = None,
        date_max: Optional[str] = None,
    ) -> list[dict]:
        """Fetch top sellers report."""
        params = {"period": period}
        if date_min:
            params["date_min"] = date_min
        if date_max:
            params["date_max"] = date_max
        return await self._get("/reports/top_sellers", params=params)

    async def get_reports(self) -> list[dict]:
        """
        Fetch available report types from WooCommerce.

        Returns a list of report endpoints that can be queried.
        """
        return await self._get("/reports")

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL — HTTP Methods with Retry Logic
    # ═══════════════════════════════════════════════════════════════

    async def _get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """Perform a GET request with retry logic."""
        url = f"{self.api_base}{endpoint}"
        return await self._request("GET", url, params=params)

    async def _post(self, endpoint: str, data: dict) -> Any:
        """Perform a POST request with retry logic."""
        url = f"{self.api_base}{endpoint}"
        return await self._request("POST", url, json=data)

    async def _put(self, endpoint: str, data: dict) -> Any:
        """Perform a PUT request with retry logic."""
        url = f"{self.api_base}{endpoint}"
        return await self._request("PUT", url, json=data)

    async def _delete(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """Perform a DELETE request with retry logic."""
        url = f"{self.api_base}{endpoint}"
        return await self._request("DELETE", url, params=params)

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Any:
        """
        Core HTTP request method with exponential backoff retry.

        Retries on:
        - 429 Too Many Requests
        - 5xx Server Errors
        - Network timeouts / connection errors

        Does NOT retry on 4xx Client Errors (except 429).

        Logs structured info for every request including:
        - Method, URL, attempt number
        - Response status code and latency
        - Error details on failure
        """
        last_exception: Optional[Exception] = None
        endpoint_summary = url.replace(self.api_base, "") if self.api_base in url else url

        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            self._request_count += 1

            try:
                client = self._get_client()
                start_time = asyncio.get_event_loop().time()

                response = await client.request(
                    method,
                    url,
                    auth=self.auth,
                    timeout=self.timeout,
                    **kwargs,
                )

                elapsed_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)

                # Success
                if response.is_success:
                    self.logger.debug(
                        "WC API OK: %s %s → %d (%dms, attempt %d/%d)",
                        method, endpoint_summary, response.status_code,
                        elapsed_ms, attempt, MAX_RETRY_ATTEMPTS,
                    )
                    return response.json()

                # Rate limited — respect Retry-After
                if response.status_code == 429:
                    retry_after = self._parse_retry_after(response)
                    self.logger.warning(
                        "WC RATE LIMITED (429): %s %s — retrying in %ds (attempt %d/%d)",
                        method, endpoint_summary, retry_after, attempt, MAX_RETRY_ATTEMPTS,
                    )
                    await asyncio.sleep(retry_after)
                    continue

                # Retryable server error
                if response.status_code in RETRYABLE_STATUSES:
                    delay = BASE_RETRY_DELAY * (2 ** (attempt - 1))
                    self.logger.warning(
                        "WC SERVER ERROR %d: %s %s — retrying in %.1fs (attempt %d/%d)",
                        response.status_code, method, endpoint_summary,
                        delay, attempt, MAX_RETRY_ATTEMPTS,
                    )
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable client error with specific error mapping
                self._error_count += 1
                error_body = response.text[:500]

                # Map HTTP status to appropriate exception type
                exc_type = HTTP_STATUS_ERROR_MAP.get(
                    response.status_code, WooCommerceAPIError
                )

                # For 404, try to determine resource type from URL
                if response.status_code == 404:
                    for resource_key, resource_exc in RESOURCE_404_MAP.items():
                        if resource_key in endpoint_summary.lower():
                            exc_type = resource_exc
                            break

                self.logger.error(
                    "WC API ERROR %d: %s %s — %s",
                    response.status_code, method, endpoint_summary, error_body[:100],
                )
                raise exc_type(response.status_code, error_body)

            except httpx.TimeoutException as exc:
                last_exception = exc
                delay = BASE_RETRY_DELAY * (2 ** (attempt - 1))
                self.logger.warning(
                    "WC TIMEOUT: %s %s — retrying in %.1fs (attempt %d/%d)",
                    method, endpoint_summary, delay, attempt, MAX_RETRY_ATTEMPTS,
                )
                await asyncio.sleep(delay)

            except httpx.NetworkError as exc:
                last_exception = exc
                delay = BASE_RETRY_DELAY * (2 ** (attempt - 1))
                self.logger.warning(
                    "WC NETWORK ERROR: %s — %s %s — retrying in %.1fs (attempt %d/%d)",
                    exc, method, endpoint_summary, delay, attempt, MAX_RETRY_ATTEMPTS,
                )
                await asyncio.sleep(delay)

        # All retries exhausted
        self._error_count += 1
        error_msg = str(last_exception) if last_exception else "Max retries exceeded"
        self.logger.error(
            "WC REQUEST FAILED after %d retries: %s %s — %s",
            MAX_RETRY_ATTEMPTS, method, endpoint_summary, error_msg,
        )
        raise WooCommerceAPIError(0, f"Request failed after {MAX_RETRY_ATTEMPTS} retries: {error_msg}")

    async def _get_paginated(
        self,
        endpoint: str,
        params: dict,
    ) -> tuple[list[dict], dict]:
        """
        Fetch a single page and return (data, headers).

        Headers include:
        - X-WP-Total: Total number of items
        - X-WP-TotalPages: Total number of pages
        """
        url = f"{self.api_base}{endpoint}"
        client = self._get_client()
        response = await client.request(
            "GET", url, auth=self.auth, timeout=self.timeout, params=params,
        )

        if not response.is_success:
            raise WooCommerceAPIError(response.status_code, response.text[:500])

        data = response.json()
        headers = {
            "total": int(response.headers.get("X-WP-Total", 0)),
            "total_pages": int(response.headers.get("X-WP-TotalPages", 0)),
        }
        return data, headers

    async def _paginate_all(
        self,
        endpoint: str,
        params: dict,
    ) -> list[dict]:
        """
        Automatically paginate through ALL pages of a WooCommerce endpoint.

        Handles cursor-based pagination implicitly via page parameter.
        Returns the complete list of all items.
        """
        all_items: list[dict] = []
        page = 1
        params["per_page"] = params.get("per_page", PRODUCTS_PER_PAGE)

        while True:
            params["page"] = page
            items, headers = await self._get_paginated(endpoint, params)
            if not items:
                break
            all_items.extend(items)

            total_pages = headers.get("total_pages", 0)
            if page >= total_pages:
                break
            page += 1

        return all_items

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL — Helpers
    # ═══════════════════════════════════════════════════════════════

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared httpx AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
            )
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
    def _parse_retry_after(response: httpx.Response) -> int:
        """Parse the Retry-After header from a rate-limited response."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return int(retry_after)
            except (ValueError, TypeError):
                pass
        return 2  # Default retry delay

    @staticmethod
    def normalize_variation(wc_variation: dict) -> dict:
        """
        Normalize a WooCommerce product variation into internal format.

        Variations have a similar structure to products but with variation-specific
        fields like attributes that define the variation (e.g., size, color).
        """
        attributes = wc_variation.get("attributes", [])

        return {
            "wc_variation_id": wc_variation.get("id"),
            "wc_product_id": wc_variation.get("parent_id", 0),
            "sku": wc_variation.get("sku", ""),
            "price": wc_variation.get("price", "0.00"),
            "regular_price": wc_variation.get("regular_price", "0.00"),
            "sale_price": wc_variation.get("sale_price", ""),
            "on_sale": wc_variation.get("on_sale", False),
            "purchasable": wc_variation.get("purchasable", True),
            "manage_stock": wc_variation.get("manage_stock", False),
            "stock_quantity": wc_variation.get("stock_quantity"),
            "stock_status": wc_variation.get("stock_status", "instock"),
            "weight": wc_variation.get("weight", ""),
            "dimensions": wc_variation.get("dimensions", {}),
            "shipping_class": wc_variation.get("shipping_class", ""),
            "tax_status": wc_variation.get("tax_status", "taxable"),
            "tax_class": wc_variation.get("tax_class", ""),
            "backorders": wc_variation.get("backorders", "no"),
            "backorders_allowed": wc_variation.get("backorders_allowed", False),
            "backordered": wc_variation.get("backordered", False),
            "image": wc_variation.get("image", {}),
            "attributes": [
                {
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "slug": a.get("slug"),
                    "option": a.get("option", ""),
                }
                for a in attributes
            ],
            "menu_order": wc_variation.get("menu_order", 0),
            "meta_data": wc_variation.get("meta_data", []),
            "date_created": wc_variation.get("date_created", ""),
            "date_modified": wc_variation.get("date_modified", ""),
            "wc_raw_data": wc_variation,
        }

    @staticmethod
    def normalize_product(wc_product: dict) -> dict:
        """
        Normalize a WooCommerce product JSON into our internal format.

        Transforms:
        - images array → featured_image_url
        - categories array → category_ids
        - tags array → tag names
        - attributes → structured attributes
        """
        images = wc_product.get("images", [])
        featured_image = images[0] if images else {}

        categories = wc_product.get("categories", [])
        tags = wc_product.get("tags", [])
        attributes = wc_product.get("attributes", [])

        return {
            "wc_product_id": wc_product.get("id"),
            "name": wc_product.get("name", ""),
            "slug": wc_product.get("slug", ""),
            "permalink": wc_product.get("permalink", ""),
            "description": wc_product.get("description", ""),
            "short_description": wc_product.get("short_description", ""),
            "sku": wc_product.get("sku", ""),
            "price": wc_product.get("price", "0.00"),
            "regular_price": wc_product.get("regular_price", "0.00"),
            "sale_price": wc_product.get("sale_price", ""),
            "price_html": wc_product.get("price_html", ""),
            "on_sale": wc_product.get("on_sale", False),
            "purchasable": wc_product.get("purchasable", True),
            "total_sales": wc_product.get("total_sales", 0),
            "virtual": wc_product.get("virtual", False),
            "downloadable": wc_product.get("downloadable", False),
            "downloads": wc_product.get("downloads", []),
            "download_limit": wc_product.get("download_limit", -1),
            "download_expiry": wc_product.get("download_expiry", -1),
            "external_url": wc_product.get("external_url", ""),
            "button_text": wc_product.get("button_text", ""),
            "tax_status": wc_product.get("tax_status", "taxable"),
            "tax_class": wc_product.get("tax_class", ""),
            "manage_stock": wc_product.get("manage_stock", False),
            "stock_quantity": wc_product.get("stock_quantity"),
            "stock_status": wc_product.get("stock_status", "instock"),
            "backorders": wc_product.get("backorders", "no"),
            "backorders_allowed": wc_product.get("backorders_allowed", False),
            "backordered": wc_product.get("backordered", False),
            "sold_individually": wc_product.get("sold_individually", False),
            "weight": wc_product.get("weight", ""),
            "dimensions": wc_product.get("dimensions", {}),
            "shipping_required": wc_product.get("shipping_required", True),
            "shipping_taxable": wc_product.get("shipping_taxable", True),
            "shipping_class": wc_product.get("shipping_class", ""),
            "shipping_class_id": wc_product.get("shipping_class_id", 0),
            "reviews_allowed": wc_product.get("reviews_allowed", True),
            "average_rating": wc_product.get("average_rating", "0"),
            "rating_count": wc_product.get("rating_count", 0),
            "related_ids": wc_product.get("related_ids", []),
            "upsell_ids": wc_product.get("upsell_ids", []),
            "cross_sell_ids": wc_product.get("cross_sell_ids", []),
            "parent_id": wc_product.get("parent_id", 0),
            "purchase_note": wc_product.get("purchase_note", ""),
            "featured": wc_product.get("featured", False),
            "featured_image_url": featured_image.get("src", ""),
            "featured_image_id": featured_image.get("id"),
            "category_ids": [c.get("id") for c in categories],
            "category_names": [c.get("name") for c in categories],
            "tag_ids": [t.get("id") for t in tags],
            "tag_names": [t.get("name") for t in tags],
            "attributes": [
                {
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "slug": a.get("slug"),
                    "position": a.get("position", 0),
                    "visible": a.get("visible", True),
                    "variation": a.get("variation", False),
                    "options": a.get("options", []),
                }
                for a in attributes
            ],
            "default_attributes": wc_product.get("default_attributes", []),
            "variations": wc_product.get("variations", []),
            "grouped_products": wc_product.get("grouped_products", []),
            "menu_order": wc_product.get("menu_order", 0),
            "meta_data": wc_product.get("meta_data", []),
            "type": wc_product.get("type", "simple"),
            "status": wc_product.get("status", "publish"),
            "date_created": wc_product.get("date_created", ""),
            "date_modified": wc_product.get("date_modified", ""),
            "wc_raw_data": wc_product,  # Preserve original payload
        }

    @staticmethod
    def normalize_order(wc_order: dict) -> dict:
        """Normalize a WooCommerce order into internal format."""
        return {
            "wc_order_id": wc_order.get("id"),
            "parent_id": wc_order.get("parent_id", 0),
            "number": wc_order.get("number", ""),
            "order_key": wc_order.get("order_key", ""),
            "status": wc_order.get("status", "pending"),
            "currency": wc_order.get("currency", "USD"),
            "date_created": wc_order.get("date_created", ""),
            "date_modified": wc_order.get("date_modified", ""),
            "date_paid": wc_order.get("date_paid"),
            "date_completed": wc_order.get("date_completed"),
            "discount_total": wc_order.get("discount_total", "0.00"),
            "discount_tax": wc_order.get("discount_tax", "0.00"),
            "shipping_total": wc_order.get("shipping_total", "0.00"),
            "shipping_tax": wc_order.get("shipping_tax", "0.00"),
            "cart_tax": wc_order.get("cart_tax", "0.00"),
            "total": wc_order.get("total", "0.00"),
            "total_tax": wc_order.get("total_tax", "0.00"),
            "prices_include_tax": wc_order.get("prices_include_tax", False),
            "customer_id": wc_order.get("customer_id", 0),
            "customer_ip_address": wc_order.get("customer_ip_address", ""),
            "customer_user_agent": wc_order.get("customer_user_agent", ""),
            "customer_note": wc_order.get("customer_note", ""),
            "billing": wc_order.get("billing", {}),
            "shipping": wc_order.get("shipping", {}),
            "payment_method": wc_order.get("payment_method", ""),
            "payment_method_title": wc_order.get("payment_method_title", ""),
            "transaction_id": wc_order.get("transaction_id", ""),
            "coupon_lines": wc_order.get("coupon_lines", []),
            "fee_lines": wc_order.get("fee_lines", []),
            "shipping_lines": wc_order.get("shipping_lines", []),
            "tax_lines": wc_order.get("tax_lines", []),
            "refunds": wc_order.get("refunds", []),
            "line_items": wc_order.get("line_items", []),
            "meta_data": wc_order.get("meta_data", []),
            "wc_raw_data": wc_order,
        }

    @staticmethod
    def normalize_customer(wc_customer: dict) -> dict:
        """Normalize a WooCommerce customer into internal format."""
        return {
            "wc_customer_id": wc_customer.get("id"),
            "email": wc_customer.get("email", ""),
            "first_name": wc_customer.get("first_name", ""),
            "last_name": wc_customer.get("last_name", ""),
            "username": wc_customer.get("username", ""),
            "role": wc_customer.get("role", "customer"),
            "billing": wc_customer.get("billing", {}),
            "shipping": wc_customer.get("shipping", {}),
            "avatar_url": wc_customer.get("avatar_url", ""),
            "date_created": wc_customer.get("date_created", ""),
            "date_modified": wc_customer.get("date_modified", ""),
            "orders_count": wc_customer.get("orders_count", 0),
            "total_spent": wc_customer.get("total_spent", "0.00"),
            "meta_data": wc_customer.get("meta_data", []),
            "wc_raw_data": wc_customer,
        }

    @staticmethod
    def normalize_category(wc_category: dict) -> dict:
        """Normalize a WooCommerce category into internal format."""
        return {
            "wc_category_id": wc_category.get("id"),
            "name": wc_category.get("name", ""),
            "slug": wc_category.get("slug", ""),
            "parent_id": wc_category.get("parent", 0),
            "description": wc_category.get("description", ""),
            "display": wc_category.get("display", "default"),
            "image": wc_category.get("image", {}),
            "menu_order": wc_category.get("menu_order", 0),
            "count": wc_category.get("count", 0),
            "wc_raw_data": wc_category,
        }

    @staticmethod
    def normalize_coupon(wc_coupon: dict) -> dict:
        """Normalize a WooCommerce coupon into internal format."""
        return {
            "wc_coupon_id": wc_coupon.get("id"),
            "code": wc_coupon.get("code", ""),
            "amount": wc_coupon.get("amount", "0.00"),
            "discount_type": wc_coupon.get("discount_type", "fixed_cart"),
            "description": wc_coupon.get("description", ""),
            "date_created": wc_coupon.get("date_created", ""),
            "date_modified": wc_coupon.get("date_modified", ""),
            "date_expires": wc_coupon.get("date_expires"),
            "usage_count": wc_coupon.get("usage_count", 0),
            "individual_use": wc_coupon.get("individual_use", False),
            "product_ids": wc_coupon.get("product_ids", []),
            "excluded_product_ids": wc_coupon.get("excluded_product_ids", []),
            "usage_limit": wc_coupon.get("usage_limit", 0),
            "usage_limit_per_user": wc_coupon.get("usage_limit_per_user", 0),
            "limit_usage_to_x_items": wc_coupon.get("limit_usage_to_x_items", 0),
            "free_shipping": wc_coupon.get("free_shipping", False),
            "product_categories": wc_coupon.get("product_categories", []),
            "excluded_product_categories": wc_coupon.get("excluded_product_categories", []),
            "exclude_sale_items": wc_coupon.get("exclude_sale_items", False),
            "minimum_amount": wc_coupon.get("minimum_amount", "0.00"),
            "maximum_amount": wc_coupon.get("maximum_amount", "0.00"),
            "email_restrictions": wc_coupon.get("email_restrictions", []),
            "used_by": wc_coupon.get("used_by", []),
            "meta_data": wc_coupon.get("meta_data", []),
            "wc_raw_data": wc_coupon,
        }
