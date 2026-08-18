import httpx
from urllib.parse import urlencode
from app.config import settings


def build_install_url(shop: str, state: str = None) -> str:
    """
    PURANA TAREEQA - ab bhi maujood hai, lekin naye managed-installation
    apps ke liye kaam nahi karega (redirect_uri whitelist error dega).
    Rakha hai reference/fallback ke liye, use nahi ho raha ab.

    state me user id bheji jati hai (user_<id>) taake /callback store ko
    sahi user ke account me save kar sake.
    """
    params = {
        "client_id": settings.SHOPIFY_API_KEY,
        "scope": settings.SHOPIFY_SCOPES,
        "redirect_uri": settings.SHOPIFY_REDIRECT_URI,
        "state": state or "random_state_string_todo",
    }
    return f"https://{shop}/admin/oauth/authorize?{urlencode(params)}"


async def exchange_code_for_token(shop: str, code: str) -> dict:
    """
    PURANA TAREEQA - /callback route ke sath use hota tha. Ab zaroorat
    nahi (naya token_exchange() function isay replace karta hai), lekin
    rakha hai taake purana /shopify/callback route na toote.
    """
    url = f"https://{shop}/admin/oauth/access_token"
    payload = {
        "client_id": settings.SHOPIFY_API_KEY,
        "client_secret": settings.SHOPIFY_API_SECRET,
        "code": code,
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


async def token_exchange(shop: str, session_token: str) -> dict:
    """
    NAYA TAREEQA - Managed Installation apps ke liye.

    Jab app Shopify admin ke andar (embedded) khulti hai, Shopify humein
    URL me ek "id_token" (JWT session token) deta hai. Hum us token ko
    is function se "exchange" karte hain asal access_token ke liye -
    koi redirect/authorize page ki zaroorat nahi.

    Docs: https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/token-exchange
    """
    url = f"https://{shop}/admin/oauth/access_token"

    payload = {
        "client_id": settings.SHOPIFY_API_KEY,
        "client_secret": settings.SHOPIFY_API_SECRET,
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": session_token,
        "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
        "requested_token_type": "urn:shopify:params:oauth:token-type:offline-access-token",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload)
        if response.status_code >= 400:
            raise Exception(
                f"Shopify said: {response.status_code} | "
                f"Headers: {dict(response.headers)} | "
                f"Body: '{response.text}' | "
                f"Payload sent: {payload}"
            )
        return response.json()


async def fetch_products(shop: str, access_token: str):
    url = f"https://{shop}/admin/api/2026-07/products.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()
