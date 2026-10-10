# ═══════════════════════════════════════════════════════════════
# tests / test_support_cart.py
#
# PURPOSE: "Add to cart" sends the NAMED product's variant and the asked quantity to
#          Shopify's Storefront API (mocked transport) and only reports success with
#          Shopify's own checkout URL. Missing token / Shopify errors hand off to a human
#          and never produce a success message or a link.
#          Uses the db_session fixture (rolled back, nothing kept).
# ═══════════════════════════════════════════════════════════════

import json

import httpx
import pytest

from src.domains.agents.customer_support.handler import CustomerSupportHandler
from src.domains.agents.customer_support.shopify_storefront_client import (
    ShopifyStorefrontClient,
    StorefrontNotConfigured,
)
from src.sdk.models.base import Product, Variant

from ._support_seed import NoLLM, OWNER_EMAIL, seed_store

CHECKOUT_URL = "https://demo-store.example/cart/c/abc123?key=k1"


class Shopify:
    """Fake Shopify Storefront endpoint: records every request, answers with `responder(body)`."""

    def __init__(self, responder=None):
        self.requests: list[httpx.Request] = []
        self.responder = responder or self.ok

    @staticmethod
    def ok(body):
        qty = body["variables"]["input"]["lines"][0]["quantity"]
        return httpx.Response(200, json={"data": {"cartCreate": {
            "cart": {"id": "gid://shopify/Cart/abc123", "checkoutUrl": CHECKOUT_URL, "totalQuantity": qty},
            "userErrors": []}}})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responder(json.loads(request.content))

    @property
    def bodies(self):
        return [json.loads(r.content) for r in self.requests]

    def client(self, token="storefront-test-token", domain="demo-store.example") -> ShopifyStorefrontClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(self))
        return ShopifyStorefrontClient(shop_domain=domain, access_token=token, http_client=http)


async def say(db, store, text, shopify=None, language="", client="default", token="storefront-test-token"):
    if client == "default":
        client = shopify.client() if shopify else None
    handler = CustomerSupportHandler(db=db, llm_client=NoLLM(), storefront_client=client)
    handler.settings.STOREFRONT_ACCESS_TOKEN = token
    return await handler.process_message(
        store_id=store.id, customer_email=OWNER_EMAIL, text=text, language=language,
        authenticated_email=OWNER_EMAIL,
    )


def sent_line(shopify):
    (body,) = shopify.bodies
    (line,) = body["variables"]["input"]["lines"]
    return line


# ─── success: exact variant + quantity, real checkout URL ──────

async def test_sends_named_variant_and_quantity_and_shows_real_checkout_url(db_session):
    store = await seed_store(db_session)
    shopify = Shopify()
    r = await say(db_session, store, "add 2 of Denim Jacket to my cart", shopify)
    assert r["intent"] == "cart_add"
    assert sent_line(shopify) == {"merchandiseId": "gid://shopify/ProductVariant/5002", "quantity": 2}  # jacket, not the tee
    assert r["content"] == f"Added 2 × Denim Jacket to your cart. You can complete checkout here: {CHECKOUT_URL}"
    assert r["conversation_status"] == "open"
    req = shopify.requests[0]
    assert str(req.url) == "https://demo-store.example/api/2024-01/graphql.json"
    assert req.headers["X-Shopify-Storefront-Access-Token"] == "storefront-test-token"


async def test_default_quantity_is_one(db_session):
    store = await seed_store(db_session)
    shopify = Shopify()
    await say(db_session, store, "add the Classic Cotton Tee to my cart", shopify)
    assert sent_line(shopify) == {"merchandiseId": "gid://shopify/ProductVariant/5001", "quantity": 1}


async def test_roman_urdu_quantity_is_parsed_and_reply_is_roman_urdu(db_session):
    store = await seed_store(db_session)
    shopify = Shopify()
    r = await say(db_session, store, "teen Denim Jacket cart me daal do", shopify, language="roman_urdu")
    assert sent_line(shopify) == {"merchandiseId": "gid://shopify/ProductVariant/5002", "quantity": 3}
    assert r["content"] == f"3 × Denim Jacket cart me add ho gaya hai! Checkout link: {CHECKOUT_URL}"


async def test_roman_urdu_daal_do_is_not_read_as_quantity_two(db_session):
    store = await seed_store(db_session)
    shopify = Shopify()
    await say(db_session, store, "Denim Jacket cart me daal do", shopify, language="roman_urdu")
    assert sent_line(shopify)["quantity"] == 1


async def test_digits_inside_product_name_are_not_a_quantity(db_session):
    store = await seed_store(db_session)
    toaster = Product(store_id=store.id, title="Toaster 9000", description="")
    db_session.add(toaster)
    await db_session.flush()
    db_session.add(Variant(product_id=toaster.id, title="Default Title", sku="T9", price=60,
                           inventory_quantity=50, platform_variant_id="gid://shopify/ProductVariant/7777"))
    await db_session.flush()
    shopify = Shopify()
    await say(db_session, store, "add Toaster 9000 to my cart", shopify)
    assert sent_line(shopify) == {"merchandiseId": "gid://shopify/ProductVariant/7777", "quantity": 1}  # existing gid kept


# ─── things that must NOT reach Shopify ────────────────────────

async def test_stock_limit_is_enforced_before_calling_shopify(db_session):
    store = await seed_store(db_session)  # jacket stock = 8
    shopify = Shopify()
    r = await say(db_session, store, "add 9 Denim Jacket to my cart", shopify)
    assert shopify.requests == []
    assert "Only 8" in r["content"] and "Added" not in r["content"] and "http" not in r["content"]
    ok = Shopify()
    await say(db_session, store, "add 8 Denim Jacket to my cart", ok)  # exactly the stock is fine
    assert sent_line(ok)["quantity"] == 8


async def test_out_of_stock_variant_is_not_added(db_session):
    store = await seed_store(db_session)
    pants = Product(store_id=store.id, title="Cargo Pants", description="")
    db_session.add(pants)
    await db_session.flush()
    db_session.add(Variant(product_id=pants.id, title="Default Title", sku="CP", price=40,
                           inventory_quantity=0, platform_variant_id="8001"))
    await db_session.flush()
    shopify = Shopify()
    r = await say(db_session, store, "add Cargo Pants to my cart", shopify)
    assert shopify.requests == [] and "out of stock" in r["content"] and "http" not in r["content"]


async def test_multi_variant_product_asks_which_option(db_session):
    store = await seed_store(db_session)
    pants = Product(store_id=store.id, title="Cargo Pants", description="")
    db_session.add(pants)
    await db_session.flush()
    db_session.add_all([Variant(product_id=pants.id, title=t, sku=f"CP-{t}", price=40, inventory_quantity=5,
                                platform_variant_id=vid) for t, vid in (("S", "8101"), ("M", "8102"), ("L", "8103"))])
    await db_session.flush()

    shopify = Shopify()
    r = await say(db_session, store, "add 2 Cargo Pants to my cart", shopify)
    assert shopify.requests == []
    assert "several options" in r["content"] and "S, M, L" in r["content"]

    shopify = Shopify()  # naming the option picks exactly that variant
    r = await say(db_session, store, "add 2 Cargo Pants in L to my cart", shopify)
    assert sent_line(shopify) == {"merchandiseId": "gid://shopify/ProductVariant/8103", "quantity": 2}
    assert "Cargo Pants (L)" in r["content"]


async def test_unknown_product_adds_nothing(db_session):
    store = await seed_store(db_session)
    shopify = Shopify()
    r = await say(db_session, store, "add 2 Quantum Toaster 9000 to my cart", shopify)
    assert shopify.requests == []
    assert "couldn't find a product called Quantum Toaster 9000" in r["content"]


async def test_quantity_zero_is_rejected(db_session):
    store = await seed_store(db_session)
    shopify = Shopify()
    r = await say(db_session, store, "add 0 Denim Jacket to my cart", shopify)
    assert shopify.requests == [] and "quantity between 1 and 99" in r["content"]


# ─── failures: hand off, never a success message or link ───────

async def test_missing_storefront_token_hands_off_without_success(db_session):
    store = await seed_store(db_session)
    r = await say(db_session, store, "add 2 of Denim Jacket to my cart", client=None, token="")
    assert r["conversation_status"] == "handoff"
    assert "isn't set up" in r["content"] and "alerted our support team" in r["content"]
    assert "Added" not in r["content"] and "http" not in r["content"] and "mock" not in r["content"].lower()


async def test_missing_storefront_token_hands_off_in_roman_urdu(db_session):
    store = await seed_store(db_session)
    r = await say(db_session, store, "teen Denim Jacket cart me daal do", client=None, token="", language="roman_urdu")
    assert r["conversation_status"] == "handoff"
    assert "set up nahi" in r["content"] and "add ho gaya" not in r["content"] and "http" not in r["content"]


@pytest.mark.parametrize(
    "responder",
    [
        lambda body: httpx.Response(500, text="boom"),
        lambda body: httpx.Response(401, json={"errors": "Invalid token"}),
        lambda body: httpx.Response(200, json={"errors": [{"message": "Throttled"}]}),
        lambda body: httpx.Response(200, text="<html>not json</html>"),
        lambda body: httpx.Response(200, json={"data": {"cartCreate": {"cart": None, "userErrors": [
            {"field": ["lines", "0"], "message": "The merchandise is not available"}]}}}),
        lambda body: httpx.Response(200, json={"data": {"cartCreate": {"cart": {"id": "x", "checkoutUrl": None,
                                                                               "totalQuantity": 2}, "userErrors": []}}}),
        # Shopify accepted fewer units than asked -> not what the customer wanted
        lambda body: httpx.Response(200, json={"data": {"cartCreate": {"cart": {"id": "x", "checkoutUrl": CHECKOUT_URL,
                                                                               "totalQuantity": 1}, "userErrors": []}}}),
    ],
    ids=["http500", "http401", "graphql-errors", "non-json", "userErrors", "no-checkout-url", "quantity-mismatch"],
)
async def test_shopify_error_hands_off_without_success_or_link(db_session, responder):
    store = await seed_store(db_session)
    shopify = Shopify(responder)
    r = await say(db_session, store, "add 2 of Denim Jacket to my cart", shopify)
    assert len(shopify.requests) == 1
    assert r["conversation_status"] == "handoff"
    assert "couldn't add that to your cart" in r["content"] and "alerted our support team" in r["content"]
    assert "Added" not in r["content"] and "http" not in r["content"] and "checkout" not in r["content"].lower()


async def test_network_failure_hands_off(db_session):
    store = await seed_store(db_session)

    def boom(body):
        raise httpx.ConnectError("no route")

    r = await say(db_session, store, "add Denim Jacket to my cart", Shopify(boom))
    assert r["conversation_status"] == "handoff" and "Added" not in r["content"]


# ─── client: no mock mode anywhere ─────────────────────────────

async def test_client_without_token_raises_and_sends_nothing():
    shopify = Shopify()
    with pytest.raises(StorefrontNotConfigured):
        await shopify.client(token="").create_cart([{"merchandiseId": "gid://x/1", "quantity": 1}])
    assert shopify.requests == []


async def test_client_has_no_dev_mode_even_for_mock_looking_input():
    shopify = Shopify()
    client = shopify.client(token="mock_abc", domain="mock-shop.example.com")
    cart = await client.create_cart([{"merchandiseId": "gid://x/1", "quantity": 1}])
    assert len(shopify.requests) == 1  # a real request was made
    assert cart["checkout_url"] == CHECKOUT_URL  # and the URL comes from Shopify's response
    assert not hasattr(client, "is_dev_mode")


async def test_client_rejects_bad_shop_domain():
    shopify = Shopify()
    with pytest.raises(StorefrontNotConfigured):
        await shopify.client(domain="not a domain/..").create_cart([{"merchandiseId": "g", "quantity": 1}])
    assert shopify.requests == []
