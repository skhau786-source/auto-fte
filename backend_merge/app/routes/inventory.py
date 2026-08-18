"""
Unified Inventory Router - team member ke inventory module ka core
value, aapke (sync) backend architecture me merge kiya gaya.

Flow: login -> store connect (Shopify/WooCommerce) -> inventory
is router me dikhta hai. Har call pehle store API se products sync
karta hai (taza data), phir database se normalized list banata hai.

Endpoints:
- GET /inventory            -> user ke connected store ka product inventory
- GET /inventory/low-stock  -> kam stock wale items (threshold based)
- GET /inventory/summary    -> totals (total / in-stock / low-stock / out-of-stock)
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.shopify_store import ShopifyStore
from app.models.woocommerce_store import WooCommerceStore
from app.models.product import Product
from app.models.woocommerce_product import WooCommerceProduct
from app.models.user import User
from app.services import shopify_service, woocommerce_service
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/inventory", tags=["Inventory"])


def _shopify_stock_status(inventory: int, threshold: int) -> str:
    if inventory <= 0:
        return "outofstock"
    if inventory <= threshold:
        return "lowstock"
    return "instock"


def _find_user_store(db: Session, user_id: int, shop: Optional[str], store_url: Optional[str]):
    """
    User ka connected store dhundta hai. Agar shop/store_url diya hai to
    usi ko use karta hai, warna user ka pehla connected store (Shopify ya
    WooCommerce) leta hai.
    """
    if shop:
        store = db.query(ShopifyStore).filter(
            ShopifyStore.shop_url == shop,
            ShopifyStore.user_id == user_id,
        ).first()
        if store:
            return ("shopify", store)
        raise HTTPException(status_code=404, detail="Shopify store not connected for this user")

    if store_url:
        store = db.query(WooCommerceStore).filter(
            WooCommerceStore.store_url == store_url,
            WooCommerceStore.user_id == user_id,
        ).first()
        if store:
            return ("woocommerce", store)
        raise HTTPException(status_code=404, detail="WooCommerce store not connected for this user")

    # Koi filter nahi -> user ka koi bhi connected store
    shopify_store = db.query(ShopifyStore).filter(ShopifyStore.user_id == user_id).first()
    if shopify_store:
        return ("shopify", shopify_store)

    wc_store = db.query(WooCommerceStore).filter(WooCommerceStore.user_id == user_id).first()
    if wc_store:
        return ("woocommerce", wc_store)

    raise HTTPException(
        status_code=404,
        detail="No store connected. Pehle Shopify ya WooCommerce store connect karein.",
    )


async def _sync_shopify(db: Session, store: ShopifyStore) -> int:
    """Shopify API se products fetch karke DB me upsert karta hai. Count return karta hai."""
    response = await shopify_service.fetch_products(store.shop_url, store.access_token)
    products = response.get("products", [])
    for p in products:
        variant = p["variants"][0] if p.get("variants") else {}
        existing = db.query(Product).filter(
            Product.shopify_product_id == str(p["id"]),
            Product.shop_id == store.id,
        ).first()
        if existing:
            existing.title = p.get("title")
            existing.vendor = p.get("vendor")
            existing.product_type = p.get("product_type")
            existing.status = p.get("status")
            existing.price = float(variant.get("price", 0) or 0)
            existing.inventory = variant.get("inventory_quantity", 0) or 0
        else:
            db.add(Product(
                shopify_product_id=str(p["id"]),
                title=p.get("title"),
                vendor=p.get("vendor"),
                product_type=p.get("product_type"),
                status=p.get("status"),
                price=float(variant.get("price", 0) or 0),
                inventory=variant.get("inventory_quantity", 0) or 0,
                shop_id=store.id,
            ))
    db.commit()
    return len(products)


async def _sync_woocommerce(db: Session, store: WooCommerceStore) -> int:
    """WooCommerce API se products fetch karke DB me upsert karta hai. Count return karta hai."""
    raw_products = await woocommerce_service.fetch_all_products(
        store.store_url, store.consumer_key, store.consumer_secret
    )
    for raw in raw_products:
        normalized = woocommerce_service.map_woocommerce_product(raw)
        existing = db.query(WooCommerceProduct).filter(
            WooCommerceProduct.woocommerce_product_id == normalized["external_id"],
            WooCommerceProduct.store_id == store.id,
        ).first()
        try:
            price_value = float(normalized["price"]) if normalized["price"] else None
        except (ValueError, TypeError):
            price_value = None
        if existing:
            existing.title = normalized["name"]
            existing.sku = normalized["sku"]
            existing.price = price_value
            existing.inventory = normalized["stock_quantity"] or 0
            existing.stock_status = normalized["stock_status"]
            existing.image_url = normalized["image_url"]
        else:
            db.add(WooCommerceProduct(
                woocommerce_product_id=normalized["external_id"],
                title=normalized["name"],
                sku=normalized["sku"],
                price=price_value,
                inventory=normalized["stock_quantity"] or 0,
                stock_status=normalized["stock_status"],
                image_url=normalized["image_url"],
                store_id=store.id,
            ))
    db.commit()
    return len(raw_products)


async def _load_products(db: Session, source: str, store, sync: bool = True):
    """
    Products load karta hai. Sync=True par pehle store API se taza data
    leke DB me save karta hai. Agar store unreachable ho (galat token,
    domain resolve na ho) to DB ka purana data de deta hai - endpoint
    kabhi hang ya crash nahi hota.
    Returns: (products, sync_error_message_or_None)
    """
    sync_error = None
    if sync:
        try:
            if source == "shopify":
                await _sync_shopify(db, store)
            else:
                await _sync_woocommerce(db, store)
        except Exception as e:
            sync_error = f"Sync failed ({type(e).__name__}): {str(e)[:200]}"
            db.rollback()

    if source == "shopify":
        products = db.query(Product).filter(Product.shop_id == store.id).all()
    else:
        products = db.query(WooCommerceProduct).filter(WooCommerceProduct.store_id == store.id).all()

    return products, sync_error


def _serialize(product, source: str, threshold: int) -> dict:
    if source == "shopify":
        inventory = product.inventory or 0
        return {
            "id": product.id,
            "source": "shopify",
            "external_id": product.shopify_product_id,
            "title": product.title,
            "sku": None,
            "price": product.price,
            "inventory": inventory,
            "stock_status": _shopify_stock_status(inventory, threshold),
            "image_url": None,
            "vendor": product.vendor,
        }
    inventory = product.inventory or 0
    status = product.stock_status
    if status in (None, ""):
        status = _shopify_stock_status(inventory, threshold)
    return {
        "id": product.id,
        "source": "woocommerce",
        "external_id": product.woocommerce_product_id,
        "title": product.title,
        "sku": product.sku,
        "price": product.price,
        "inventory": inventory,
        "stock_status": status,
        "image_url": product.image_url,
        "vendor": None,
    }


@router.get("")
async def get_inventory(
    shop: Optional[str] = Query(None, description="Shopify store domain (optional)"),
    store_url: Optional[str] = Query(None, description="WooCommerce store URL (optional)"),
    search: Optional[str] = Query(None, max_length=200),
    low_stock_only: bool = Query(False, description="Sirf low-stock items"),
    threshold: int = Query(10, ge=0, description="Low-stock threshold"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    User ke connected store ka inventory list karta hai.
    Pehle store API se sync (taza data), phir database se list.
    """
    source, store = _find_user_store(db, current_user.id, shop, store_url)

    products, sync_error = await _load_products(db, source, store)

    if search:
        products = [p for p in products if search.lower() in (p.title or "").lower()
                    or (getattr(p, "sku", None) and search.lower() in (p.sku or "").lower())]

    items = [_serialize(p, source, threshold) for p in products]

    if low_stock_only:
        items = [i for i in items if i["stock_status"] in ("lowstock", "outofstock")]

    total = len(items)
    start = (page - 1) * page_size
    return {
        "store_type": source,
        "store": store.shop_url if source == "shopify" else store.store_url,
        "total": total,
        "page": page,
        "page_size": page_size,
        "sync_error": sync_error,
        "items": items[start:start + page_size],
    }


@router.get("/low-stock")
async def get_low_stock(
    shop: Optional[str] = Query(None),
    store_url: Optional[str] = Query(None),
    threshold: int = Query(10, ge=0, description="Low-stock threshold (default 10)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Kam stock wale items - threshold se kam ya barabar inventory.
    Team member ke inventory module ka low-stock feature, sync version.
    """
    source, store = _find_user_store(db, current_user.id, shop, store_url)

    products, sync_error = await _load_products(db, source, store)

    items = []
    for p in products:
        serialized = _serialize(p, source, threshold)
        inventory = p.inventory or 0
        if source == "shopify":
            is_low = inventory <= threshold
        else:
            status = p.stock_status or ""
            is_low = inventory <= threshold or status == "outofstock"
        if is_low:
            items.append(serialized)

    items.sort(key=lambda i: i["inventory"])
    return {
        "store_type": source,
        "store": store.shop_url if source == "shopify" else store.store_url,
        "threshold": threshold,
        "total": len(items),
        "sync_error": sync_error,
        "items": items,
    }


@router.get("/summary")
async def get_summary(
    shop: Optional[str] = Query(None),
    store_url: Optional[str] = Query(None),
    threshold: int = Query(10, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Store ki inventory ka quick dashboard - total / in-stock / low-stock / out-of-stock.
    """
    source, store = _find_user_store(db, current_user.id, shop, store_url)

    products, sync_error = await _load_products(db, source, store)

    total_products = len(products)
    total_units = 0
    in_stock = 0
    low_stock = 0
    out_of_stock = 0

    for p in products:
        inventory = p.inventory or 0
        total_units += inventory
        if source == "shopify":
            status = _shopify_stock_status(inventory, threshold)
        else:
            status = p.stock_status or _shopify_stock_status(inventory, threshold)

        if status == "outofstock":
            out_of_stock += 1
        elif status == "lowstock":
            low_stock += 1
        else:
            in_stock += 1

    return {
        "store_type": source,
        "store": store.shop_url if source == "shopify" else store.store_url,
        "threshold": threshold,
        "total_products": total_products,
        "total_inventory_units": total_units,
        "in_stock": in_stock,
        "low_stock": low_stock,
        "out_of_stock": out_of_stock,
        "sync_error": sync_error,
    }
