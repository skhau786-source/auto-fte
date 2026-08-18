from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.shopify_store import ShopifyStore
from app.models.product import Product
from app.models.user import User
from app.services import shopify_service
from app.services.auth_service import get_current_user

router = APIRouter(
    prefix="/shopify",
    tags=["Shopify"]
)


def _user_id_from_state(state: str) -> int:
    """
    /connect state me 'user_<id>' bhejta hai; /callback isay parse
    karta hai taake store sahi user ke account me save ho.
    """
    if state and state.startswith("user_"):
        try:
            return int(state.split("_", 1)[1])
        except ValueError:
            pass
    raise HTTPException(status_code=400, detail="Invalid or missing state (user_id) in callback")

# =========================================================
# PURANE ROUTES (redirect/authorize flow) - abhi bhi maujood
# hain, lekin naye managed-installation apps ke liye kaam
# nahi karenge. Koi nuqsan nahi, bas use nahi honge.
# =========================================================

@router.get("/connect")
def connect_shopify(shop: str, current_user: User = Depends(get_current_user)):
    if not shop.endswith(".myshopify.com"):
        raise HTTPException(status_code=400, detail="Invalid shop domain")
    install_url = shopify_service.build_install_url(shop, state=f"user_{current_user.id}")
    return RedirectResponse(url=install_url)


@router.get("/callback")
async def shopify_callback(shop: str, code: str, state: str = None, db: Session = Depends(get_db)):
    user_id = _user_id_from_state(state)
    token_data = await shopify_service.exchange_code_for_token(shop, code)
    existing = db.query(ShopifyStore).filter(ShopifyStore.shop_url == shop).first()
    if existing:
        existing.access_token = token_data["access_token"]
        existing.scope = token_data.get("scope")
        existing.user_id = user_id
    else:
        existing = ShopifyStore(
            user_id=user_id,
            shop_url=shop,
            access_token=token_data["access_token"],
            scope=token_data.get("scope"),
        )
        db.add(existing)
    db.commit()
    db.refresh(existing)
    return {"message": "Shopify store connected successfully", "shop": existing.shop_url}


# =========================================================
# NAYA ROUTE - TOKEN EXCHANGE (Managed Installation apps ke
# liye asal tareeqa). Ye tab call hota hai jab app Shopify
# admin ke andar (embedded) khulti hai aur Shopify humein
# id_token deta hai.
# =========================================================

@router.get("/session-auth", response_class=HTMLResponse)
async def session_auth(shop: str, id_token: str, user_id: int = None, db: Session = Depends(get_db)):
    """
    Shopify jab embedded app load karta hai, is route ko id_token ke
    sath call karta hai (main.py ka root route isay yahan redirect
    karta hai). Hum id_token ko asal access_token se exchange karte
    hain aur database me save karte hain -    koi user-facing redirect ya authorize page nahi.
    """
    if user_id is None:
        return HTMLResponse(
            content="<h2>Login required</h2><p>session-auth me 'user_id' parameter chahiye. Pehle login karein, phir store connect karein.</p>",
            status_code=400,
        )

    try:
        token_data = await shopify_service.token_exchange(shop, id_token)
    except Exception as e:
        return HTMLResponse(
            content=f"<h2>Token exchange failed</h2><p>{str(e)}</p>",
            status_code=400,
        )

    access_token = token_data.get("access_token")
    scope = token_data.get("scope")

    if not access_token:
        return HTMLResponse(
            content=f"<h2>No access token received</h2><pre>{token_data}</pre>",
            status_code=400,
        )

    existing = db.query(ShopifyStore).filter(ShopifyStore.shop_url == shop).first()

    if existing:
        existing.access_token = access_token
        existing.scope = scope
        existing.user_id = user_id
    else:
        existing = ShopifyStore(
            user_id=user_id,
            shop_url=shop,
            access_token=access_token,
            scope=scope,
        )
        db.add(existing)

    db.commit()

    # Temporary success page - baad me real frontend/dashboard yahan
    # dikhega. Abhi ke liye sirf confirmation.
    return """
    <html>
        <body style="font-family: sans-serif; text-align: center; padding-top: 100px;">
            <h1 style="color: green;">✅ Shopify Store Connected!</h1>
            <p>Access token successfully saved.</p>
        </body>
    </html>
    """


# =========================================================
# STATUS + PRODUCTS (waise hi hain, koi change nahi)
# =========================================================

@router.get("/status")
def connection_status(shop: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    store = db.query(ShopifyStore).filter(
        ShopifyStore.shop_url == shop,
        ShopifyStore.user_id == current_user.id,
    ).first()
    if store:
        return {"connected": True, "shop": store.shop_url}
    return {"connected": False, "shop": shop}


@router.get("/products")
async def get_products(shop: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    store = db.query(ShopifyStore).filter(
        ShopifyStore.shop_url == shop,
        ShopifyStore.user_id == current_user.id,
    ).first()
    if not store:
        raise HTTPException(status_code=404, detail="Shopify store not connected")

    response = await shopify_service.fetch_products(store.shop_url, store.access_token)
    products = response.get("products", [])

    for p in products:
        variant = p["variants"][0] if p["variants"] else {}
        existing = db.query(Product).filter(Product.shopify_product_id == str(p["id"])).first()

        if existing:
            existing.title = p.get("title")
            existing.vendor = p.get("vendor")
            existing.product_type = p.get("product_type")
            existing.status = p.get("status")
            existing.price = float(variant.get("price", 0))
            existing.inventory = variant.get("inventory_quantity", 0)
        else:
            new_product = Product(
                shopify_product_id=str(p["id"]),
                title=p.get("title"),
                vendor=p.get("vendor"),
                product_type=p.get("product_type"),
                status=p.get("status"),
                price=float(variant.get("price", 0)),
                inventory=variant.get("inventory_quantity", 0),
                shop_id=store.id,
            )
            db.add(new_product)

    db.commit()

    return {
        "message": f"{len(products)} products synced successfully",
        "count": len(products),
        "products": products,
    }


@router.get("/synced-products")
def get_synced_products(shop: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Database se synced products ki list - WooCommerce ke /synced-products
    jaisa. Pehle /products (sync) call karo, phir yahan se read karo.
    Inventory quantity ke sath.
    """
    store = db.query(ShopifyStore).filter(
        ShopifyStore.shop_url == shop,
        ShopifyStore.user_id == current_user.id,
    ).first()
    if not store:
        raise HTTPException(status_code=404, detail="Shopify store not connected")

    products = db.query(Product).filter(Product.shop_id == store.id).all()

    return {
        "store": store.shop_url,
        "total_products": len(products),
        "products": [
            {
                "id": p.id,
                "shopify_product_id": p.shopify_product_id,
                "title": p.title,
                "vendor": p.vendor,
                "product_type": p.product_type,
                "status": p.status,
                "price": p.price,
                "inventory": p.inventory,
            }
            for p in products
        ],
    }
