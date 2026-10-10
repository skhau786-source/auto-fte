# ═══════════════════════════════════════════════════════════════
# tests / _support_seed.py
#
# PURPOSE: Throw-away store, catalog and orders for support-bot tests.
#          Rows live only inside the db_session fixture's transaction
#          (rolled back after every test).
# ═══════════════════════════════════════════════════════════════

import uuid
from datetime import datetime, timezone

from src.sdk.llm.client import LLMClient
from src.sdk.models.base import Order, Product, Store, Variant
from src.domains.agents.customer_support.handler import CustomerSupportHandler

OWNER_EMAIL = "owner.customer@example.com"
OTHER_EMAIL = "someone.else@example.com"


class NoLLM:
    """LLM unavailable -> handler uses its deterministic catalog/order answers."""

    async def generate(self, *args, **kwargs):
        from src.sdk.exceptions import LLMError

        raise LLMError("no key")


async def seed_store(db) -> Store:
    store = Store(
        platform="shopify",
        name="Test store",
        shop_name="test-store",
        shop_domain=f"test-{uuid.uuid4().hex[:8]}.example",
        access_token="not-a-real-token",
        is_active=True,
    )
    db.add(store)
    await db.flush()

    tee = Product(store_id=store.id, title="Classic Cotton Tee", description="A soft tee for the summer")
    jacket = Product(store_id=store.id, title="Denim Jacket", description="Classic denim jacket made for the cold")
    db.add_all([tee, jacket])
    await db.flush()
    db.add_all(
        [
            Variant(product_id=tee.id, title="M", sku="TEE-M", price=24.99, inventory_quantity=142),
            Variant(product_id=jacket.id, title="L", sku="JKT-L", price=89.99, inventory_quantity=8),
        ]
    )

    now = datetime.now(timezone.utc)
    db.add_all(
        [
            Order(store_id=store.id, order_number="1001", platform_order_id="gid://shopify/Order/9001001",
                  customer_email=OWNER_EMAIL, total_price=50, fulfillment_status="shipped",
                  financial_status="paid", ordered_at=now),
            Order(store_id=store.id, order_number="1002", platform_order_id="gid://shopify/Order/9001002",
                  customer_email=OTHER_EMAIL, total_price=75, fulfillment_status="fulfilled",
                  financial_status="paid", ordered_at=now),
        ]
    )
    await db.flush()
    return store


def make_handler(db) -> CustomerSupportHandler:
    return CustomerSupportHandler(db=db, llm_client=NoLLM())


async def chat(db, store, text, *, language="", authenticated_email=OWNER_EMAIL, public=False) -> dict:
    return await make_handler(db).process_message(
        store_id=store.id,
        customer_email=authenticated_email or "guest@customer.com",
        text=text,
        language=language,
        public=public,
        authenticated_email=authenticated_email,
    )
