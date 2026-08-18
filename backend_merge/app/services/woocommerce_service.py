import httpx


def _normalize_store_url(store_url: str) -> str:
    store_url = store_url.strip()
    if not store_url.startswith("http://") and not store_url.startswith("https://"):
        store_url = "https://" + store_url
    if store_url.endswith("/"):
        store_url = store_url[:-1]
    return store_url


async def test_connection(store_url: str, consumer_key: str, consumer_secret: str) -> dict:
    store_url = _normalize_store_url(store_url)
    url = f"{store_url}/wp-json/wc/v3/products"
    async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
        response = await client.get(
            url,
            params={"consumer_key": consumer_key, "consumer_secret": consumer_secret, "per_page": 1},
        )
        response.raise_for_status()
        return response.json()


async def fetch_all_products(store_url: str, consumer_key: str, consumer_secret: str) -> list:
    store_url = _normalize_store_url(store_url)
    url = f"{store_url}/wp-json/wc/v3/products"
    all_products = []
    page = 1
    async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
        while True:
            response = await client.get(
                url,
                params={"consumer_key": consumer_key, "consumer_secret": consumer_secret, "per_page": 100, "page": page},
            )
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            all_products.extend(batch)
            page += 1
            if page > 20:
                break
    return all_products


def map_woocommerce_product(raw_product: dict) -> dict:
    return {
        "source": "woocommerce",
        "external_id": str(raw_product.get("id")),
        "name": raw_product.get("name"),
        "sku": raw_product.get("sku"),
        "price": raw_product.get("price"),
        "stock_quantity": raw_product.get("stock_quantity"),
        "stock_status": raw_product.get("stock_status"),
        "image_url": (
            raw_product["images"][0]["src"]
            if raw_product.get("images") else None
        ),
    }