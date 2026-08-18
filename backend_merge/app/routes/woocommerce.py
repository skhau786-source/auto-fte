from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from urllib.parse import urlencode, quote
from app.database import get_db
from app.models.woocommerce_store import WooCommerceStore
from app.models.woocommerce_product import WooCommerceProduct
from app.models.user import User
from app.services import woocommerce_service
from app.services.auth_service import get_current_user
from app.config import settings

router = APIRouter(prefix="/woocommerce", tags=["WooCommerce"])


class WooCommerceConnectRequest(BaseModel):
    store_url: str
    consumer_key: str
    consumer_secret: str


@router.post("/connect")
async def connect_woocommerce(payload: WooCommerceConnectRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        await woocommerce_service.test_connection(
            payload.store_url, payload.consumer_key, payload.consumer_secret
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(e)}")

    existing = db.query(WooCommerceStore).filter(
        WooCommerceStore.store_url == payload.store_url
    ).first()

    if existing:
        existing.consumer_key = payload.consumer_key
        existing.consumer_secret = payload.consumer_secret
        existing.user_id = current_user.id
    else:
        existing = WooCommerceStore(
            user_id=current_user.id,
            store_url=payload.store_url,
            consumer_key=payload.consumer_key,
            consumer_secret=payload.consumer_secret,
        )
        db.add(existing)

    db.commit()
    db.refresh(existing)

    return {
        "message": "WooCommerce store connected successfully",
        "store": existing.store_url,
    }


def _normalize_store_url(store_url: str) -> str:
    store_url = store_url.strip()
    if not store_url.startswith("http://") and not store_url.startswith("https://"):
        store_url = "https://" + store_url
    if store_url.endswith("/"):
        store_url = store_url[:-1]
    return store_url


@router.get("/connect-auto")
def connect_woocommerce_auto(store_url: str, user_id: int = 1):
    """
    TEMPORARY: frontend banne tak user_id query param se aayega
    (default=1). Baad me current_user: User = Depends(get_current_user) se
    replace karna.
    """
    store_url = _normalize_store_url(store_url)

    callback_url = f"{settings.BACKEND_PUBLIC_URL}/woocommerce/callback?store_url={quote(store_url, safe='')}&user_id={user_id}"

    return_url = settings.FRONTEND_SUCCESS_URL

    params = {
        "app_name": "Digital FTE",
        "scope": "read",
        "user_id": user_id,
        "return_url": return_url,
        "callback_url": callback_url,
    }

    authorize_url = f"{store_url}/wc-auth/v1/authorize?{urlencode(params)}"

    return RedirectResponse(authorize_url)


@router.post("/callback")
async def woocommerce_auto_callback(request: Request, db: Session = Depends(get_db)):
    data = await request.json()

    consumer_key = data.get("consumer_key")
    consumer_secret = data.get("consumer_secret")

    if not consumer_key or not consumer_secret:
        raise HTTPException(status_code=400, detail="Invalid callback data from WooCommerce")

    store_url = request.query_params.get("store_url")
    if not store_url:
        raise HTTPException(status_code=400, detail="Could not determine store URL")

    user_id = request.query_params.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Could not determine user (user_id missing)")

    existing = db.query(WooCommerceStore).filter(
        WooCommerceStore.store_url == store_url
    ).first()

    if existing:
        existing.consumer_key = consumer_key
        existing.consumer_secret = consumer_secret
        existing.user_id = int(user_id)
    else:
        existing = WooCommerceStore(
            user_id=int(user_id),
            store_url=store_url,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
        )
        db.add(existing)

    db.commit()

    return {"message": "received"}


@router.get("/connected", response_class=HTMLResponse)
def connected_success_page():
    return """
    <html>
        <body style="font-family: sans-serif; text-align: center; padding-top: 100px;">
            <h1 style="color: green;">Store Connected Successfully!</h1>
            <p>Aap ab is window ko band kar sakte hain.</p>
        </body>
    </html>
    """


@router.get("/products")
async def get_products(store_url: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    store = db.query(WooCommerceStore).filter(
        WooCommerceStore.store_url == store_url,
        WooCommerceStore.user_id == current_user.id,
    ).first()

    if not store:
        raise HTTPException(status_code=404, detail="Store not connected yet")

    raw_products = await woocommerce_service.fetch_all_products(
        store.store_url, store.consumer_key, store.consumer_secret
    )

    normalized = [woocommerce_service.map_woocommerce_product(p) for p in raw_products]

    return {
        "store": store.store_url,
        "total_products": len(normalized),
        "products": normalized,
    }


@router.post("/sync-products")
async def sync_products(store_url: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    store = db.query(WooCommerceStore).filter(
        WooCommerceStore.store_url == store_url,
        WooCommerceStore.user_id == current_user.id,
    ).first()

    if not store:
        raise HTTPException(status_code=404, detail="Store not connected yet")

    raw_products = await woocommerce_service.fetch_all_products(
        store.store_url, store.consumer_key, store.consumer_secret
    )

    synced_count = 0
    updated_count = 0

    for raw in raw_products:
        normalized = woocommerce_service.map_woocommerce_product(raw)

        existing_product = db.query(WooCommerceProduct).filter(
            WooCommerceProduct.woocommerce_product_id == normalized["external_id"],
            WooCommerceProduct.store_id == store.id,
        ).first()

        try:
            price_value = float(normalized["price"]) if normalized["price"] else None
        except (ValueError, TypeError):
            price_value = None

        if existing_product:
            existing_product.title = normalized["name"]
            existing_product.sku = normalized["sku"]
            existing_product.price = price_value
            existing_product.inventory = normalized["stock_quantity"] or 0
            existing_product.stock_status = normalized["stock_status"]
            existing_product.image_url = normalized["image_url"]
            updated_count += 1
        else:
            new_product = WooCommerceProduct(
                woocommerce_product_id=normalized["external_id"],
                title=normalized["name"],
                sku=normalized["sku"],
                price=price_value,
                inventory=normalized["stock_quantity"] or 0,
                stock_status=normalized["stock_status"],
                image_url=normalized["image_url"],
                store_id=store.id,
            )
            db.add(new_product)
            synced_count += 1

    db.commit()

    return {
        "message": "Products synced successfully",
        "store": store.store_url,
        "new_products_added": synced_count,
        "existing_products_updated": updated_count,
        "total_products_processed": len(raw_products),
    }


@router.get("/synced-products")
def get_synced_products(store_url: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    store = db.query(WooCommerceStore).filter(
        WooCommerceStore.store_url == store_url,
        WooCommerceStore.user_id == current_user.id,
    ).first()

    if not store:
        raise HTTPException(status_code=404, detail="Store not connected yet")

    products = db.query(WooCommerceProduct).filter(
        WooCommerceProduct.store_id == store.id
    ).all()

    return {
        "store": store.store_url,
        "total_products": len(products),
        "products": [
            {
                "id": p.id,
                "woocommerce_product_id": p.woocommerce_product_id,
                "title": p.title,
                "sku": p.sku,
                "price": p.price,
                "inventory": p.inventory,
                "stock_status": p.stock_status,
                "image_url": p.image_url,
            }
            for p in products
        ],
    }
