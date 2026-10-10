# ═══════════════════════════════════════════════════════════════
# tests / test_support_product_match.py
#
# PURPOSE: Product questions are answered only for products whose TITLE
#          the customer names; unknown products get a "not found" reply
#          (English + Roman Urdu) and never an invented/first product.
#          Uses the db_session fixture (rolled back, nothing kept).
# ═══════════════════════════════════════════════════════════════

from src.sdk.models.base import Product, Variant

from ._support_seed import chat, seed_store


async def test_known_product_english_price_and_stock_from_db(db_session):
    store = await seed_store(db_session)
    r = await chat(db_session, store, "How much is the Denim Jacket?")
    assert "Denim Jacket" in r["content"]
    assert "$89.99" in r["content"] and "8 available" in r["content"]


async def test_known_product_roman_urdu_price_and_stock_from_db(db_session):
    store = await seed_store(db_session)
    r = await chat(db_session, store, "Denim Jacket ki qeemat kya hai?")
    assert r["intent"] == "product_question"
    assert "Denim Jacket" in r["content"]
    assert "$89.99" in r["content"] and "8 units" in r["content"]


async def test_stock_question_for_known_product(db_session):
    store = await seed_store(db_session)
    r = await chat(db_session, store, "Do you have the Classic Cotton Tee in stock?")
    assert "Classic Cotton Tee" in r["content"] and "142 available" in r["content"]


async def test_plural_and_extra_words_still_match(db_session):
    store = await seed_store(db_session)
    r = await chat(db_session, store, "what is the price of denim jackets")
    assert "Denim Jacket" in r["content"] and "$89.99" in r["content"]


async def test_unknown_product_english_says_not_found(db_session):
    store = await seed_store(db_session)
    r = await chat(db_session, store, "How much is the Quantum Toaster 9000?")
    assert r["content"] == "I couldn't find a product called Quantum Toaster 9000."
    assert "$" not in r["content"] and "stock" not in r["content"].lower()


async def test_unknown_product_roman_urdu_says_not_found(db_session):
    store = await seed_store(db_session)
    r = await chat(db_session, store, "Quantum Toaster 9000 ki qeemat kya hai?")
    assert r["content"] == "Quantum Toaster 9000 naam ka koi product nahi mila."
    assert "$" not in r["content"]


async def test_unknown_product_with_stock_wording_does_not_return_first_product(db_session):
    store = await seed_store(db_session)
    r = await chat(db_session, store, "Do you have the Zorblax Hoverboard in stock?")
    assert r["content"] == "I couldn't find a product called Zorblax Hoverboard."
    assert "Classic Cotton Tee" not in r["content"] and "$24.99" not in r["content"]


async def test_description_words_do_not_match_a_product(db_session):
    store = await seed_store(db_session)
    # "summer" appears only in the Tee's DESCRIPTION; only titles count.
    r = await chat(db_session, store, "Do you have anything for summer in stock?")
    assert "Classic Cotton Tee" not in r["content"]
    assert "couldn't find a product" in r["content"]


async def test_partial_name_overlap_is_not_enough(db_session):
    store = await seed_store(db_session)
    oven = Product(store_id=store.id, title="Toaster Oven", description="Bakes")
    db_session.add(oven)
    await db_session.flush()
    db_session.add(Variant(product_id=oven.id, title="std", sku="OVN", price=60, inventory_quantity=3))
    await db_session.flush()
    # Only "toaster" overlaps; "Quantum" and "9000" don't -> not the Toaster Oven.
    r = await chat(db_session, store, "How much is the Quantum Toaster 9000?")
    assert "Toaster Oven" not in r["content"] and "$60" not in r["content"]
    assert r["content"] == "I couldn't find a product called Quantum Toaster 9000."


async def test_price_question_without_a_product_name_asks_which_product(db_session):
    store = await seed_store(db_session)
    r = await chat(db_session, store, "How much does it cost?")
    assert "Which product" in r["content"]
    assert "$" not in r["content"]
    r = await chat(db_session, store, "kitna hai qeemat?", language="roman_urdu")
    assert "$" not in r["content"] and "naam" in r["content"]


async def test_empty_catalog_does_not_invent_products(db_session):
    import uuid

    from src.sdk.models.base import Store

    empty = Store(platform="shopify", name="Empty", shop_name="empty", shop_domain=f"empty-{uuid.uuid4().hex[:8]}.example",
                  access_token="not-a-real-token", is_active=True)
    db_session.add(empty)
    await db_session.flush()
    r = await chat(db_session, empty, "How much is the Denim Jacket?")
    assert "no products" in r["content"] and "$" not in r["content"]
