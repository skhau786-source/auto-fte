# ═══════════════════════════════════════════════════════════════
# tests / test_support_order_privacy.py
#
# PURPOSE: Order lookup only shows the logged-in user's own orders,
#          matches the order number exactly, and answers identically
#          for "missing" and "someone else's" orders.
#          Uses the db_session fixture (rolled back, nothing kept).
# ═══════════════════════════════════════════════════════════════

from ._support_seed import OTHER_EMAIL, OWNER_EMAIL, chat, seed_store

NOT_FOUND_EN = "I couldn't find that order on your account."
NOT_FOUND_RU = "Aapke account par yeh order nahi mila."


async def test_owner_sees_own_order(db_session):
    store = await seed_store(db_session)
    r = await chat(db_session, store, "Where is my order #1001?")
    assert "#1001" in r["content"] and "shipped" in r["content"]


async def test_other_users_order_gets_same_reply_as_missing_order(db_session):
    store = await seed_store(db_session)
    others = await chat(db_session, store, "Where is my order #1002?")  # exists, belongs to OTHER_EMAIL
    missing = await chat(db_session, store, "Where is my order #999999?")  # does not exist
    assert others["content"] == missing["content"] == NOT_FOUND_EN
    assert "75" not in others["content"] and "fulfilled" not in others["content"]


async def test_not_found_reply_is_identical_in_roman_urdu(db_session):
    store = await seed_store(db_session)
    others = await chat(db_session, store, "Mera order #1002 kahan hai?", language="roman_urdu")
    missing = await chat(db_session, store, "Mera order #999999 kahan hai?", language="roman_urdu")
    assert others["content"] == missing["content"] == NOT_FOUND_RU


async def test_partial_order_number_is_not_matched(db_session):
    store = await seed_store(db_session)
    # "001" is a substring of order 1001 and of platform id ...9001001, but must not match either.
    r = await chat(db_session, store, "Where is my order #001?")
    assert r["content"] == NOT_FOUND_EN
    r = await chat(db_session, store, "Where is my order #9001001?")
    assert r["content"] == NOT_FOUND_EN


async def test_identity_comes_from_auth_not_from_chat_text(db_session):
    store = await seed_store(db_session)
    # Typing the other customer's email must not unlock their order.
    r = await chat(db_session, store, f"Where is my order #1002? my email is {OTHER_EMAIL}")
    assert r["content"] == NOT_FOUND_EN
    r = await chat(db_session, store, f"order status for {OTHER_EMAIL}")
    assert r["content"] == NOT_FOUND_EN


async def test_own_email_without_number_returns_own_latest_order(db_session):
    store = await seed_store(db_session)
    r = await chat(db_session, store, f"order status for {OWNER_EMAIL}")
    assert "#1001" in r["content"]


async def test_other_user_cannot_see_owner_order(db_session):
    store = await seed_store(db_session)
    r = await chat(db_session, store, "Where is my order #1001?", authenticated_email=OTHER_EMAIL)
    assert r["content"] == NOT_FOUND_EN


async def test_no_authenticated_identity_fails_closed(db_session):
    store = await seed_store(db_session)
    r = await chat(db_session, store, "Where is my order #1001?", authenticated_email=None)
    assert r["content"] == NOT_FOUND_EN


async def test_public_visitor_still_escalates_order_questions(db_session):
    store = await seed_store(db_session)
    r = await chat(db_session, store, "Where is my order #1001?", authenticated_email=None, public=True)
    assert "escalated" in r["content"]
    assert r["conversation_status"] == "handoff"
