# ═══════════════════════════════════════════════════════════════
# tests / test_public_chat.py
#
# PURPOSE: Public website chat ke pure-logic hisse: rate limiter, client IP,
#          tokens, aur public mode mein order lookup / cart ka band hona.
#          (End-to-end HTTP behaviour live test mein jaancha gaya.)
# ═══════════════════════════════════════════════════════════════

from starlette.requests import Request

from src.domains.security.sliding_window import SlidingWindowLimiter, client_ip
from src.domains.chatbot.public_chat_service import (
    KEY_PREFIX,
    SESSION_PREFIX,
    generate_public_key,
    generate_session_token,
    hash_token,
)
from tests.test_support_handoff import FakeSession, conv


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


# ─── Rate limiter ─────────────────────────────────────────────

def test_limiter_allows_up_to_limit_then_blocks_with_retry_after():
    clock = Clock()
    limiter = SlidingWindowLimiter(clock)
    for _ in range(3):
        assert limiter.hit("k", 3, 60) == (True, 0)
    allowed, retry = limiter.hit("k", 3, 60)
    assert allowed is False
    assert 1 <= retry <= 60


def test_limiter_window_slides():
    clock = Clock()
    limiter = SlidingWindowLimiter(clock)
    for _ in range(3):
        limiter.hit("k", 3, 60)
    clock.now += 30
    assert limiter.hit("k", 3, 60)[0] is False
    assert limiter.hit("k", 3, 60)[1] == 30  # pehli hit ko 30s aur lagenge
    clock.now += 31
    assert limiter.hit("k", 3, 60)[0] is True


def test_limiter_keys_are_independent():
    limiter = SlidingWindowLimiter(Clock())
    for _ in range(2):
        limiter.hit("ip:1", 2, 60)
    assert limiter.hit("ip:1", 2, 60)[0] is False
    assert limiter.hit("ip:2", 2, 60)[0] is True


def test_limiter_garbage_collects_idle_keys():
    clock = Clock()
    limiter = SlidingWindowLimiter(clock)
    for i in range(499):
        limiter.hit(f"k{i}", 5, 10)
    clock.now += 100
    limiter.hit("fresh", 5, 10)  # 500vi call gc chalati hai
    assert set(limiter._hits) == {"fresh"}


# ─── 429 handler ──────────────────────────────────────────────

async def test_plain_http_429_becomes_a_429_response_with_retry_after():
    import json

    from fastapi import HTTPException

    from src.domains.security.rate_limit_handler import handle_429

    exc = HTTPException(status_code=429, detail="Slow down", headers={"Retry-After": "12"})
    response = await handle_429(make_request(), exc)
    assert response.status_code == 429
    assert json.loads(response.body) == {"detail": "Slow down"}
    assert response.headers["Retry-After"] == "12"


async def test_429_without_headers_still_works():
    from fastapi import HTTPException

    from src.domains.security.rate_limit_handler import handle_429

    response = await handle_429(make_request(), HTTPException(status_code=429, detail="x"))
    assert response.status_code == 429


# ─── Client IP ────────────────────────────────────────────────

def make_request(client_host="203.0.113.7", xff=None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "headers": headers, "client": (client_host, 5000), "method": "GET", "path": "/"})


def test_forwarded_header_is_ignored_unless_proxy_trusted():
    req = make_request(xff="1.2.3.4")  # visitor ne khud likh diya (spoof)
    assert client_ip(req, trust_proxy_headers=False) == "203.0.113.7"


def test_trusted_proxy_uses_rightmost_forwarded_entry():
    req = make_request(xff="6.6.6.6, 198.51.100.9")  # leftmost spoofable; rightmost proxy ne jora
    assert client_ip(req, trust_proxy_headers=True) == "198.51.100.9"


def test_trusted_proxy_without_header_falls_back_to_socket():
    assert client_ip(make_request(), trust_proxy_headers=True) == "203.0.113.7"


# ─── Keys & tokens ────────────────────────────────────────────

def test_public_key_and_session_token_shapes():
    key, token = generate_public_key(), generate_session_token()
    assert key.startswith(KEY_PREFIX) and len(key) > 20
    assert token.startswith(SESSION_PREFIX) and len(token) > 40
    assert generate_public_key() != key and generate_session_token() != token


def test_token_hash_is_stable_and_not_the_token():
    token = generate_session_token()
    assert hash_token(token) == hash_token(token)
    assert hash_token(token) != token and len(hash_token(token)) == 64
    assert hash_token(token) != hash_token(token + "x")


# ─── Public mode: order lookup / cart band ────────────────────

from src.domains.agents.customer_support.handler import CustomerSupportHandler  # noqa: E402


class SilentLLM:
    async def generate(self, *args, **kwargs):
        from src.sdk.exceptions import LLMError
        raise LLMError("no key")


def public_handler(session, calls):
    handler = CustomerSupportHandler(db=session, llm_client=SilentLLM())

    async def lookup(store_id, text, language="en"):
        calls.append("lookup_order_status")
        return "ORDER DATA"

    async def cart(store_id, conversation_id, text, language="en"):
        calls.append("add_to_cart")
        return "CART DONE"

    async def handoff(conversation_id, reason):
        calls.append(("handoff", reason))

    async def no_hits(store_id, query):
        return []

    handler.lookup_order_status, handler.add_to_cart = lookup, cart
    handler.handoff_to_human, handler._knowledge_hits = handoff, no_hits
    return handler


async def run(handler, text, public):
    return await handler.process_message(
        store_id=1, customer_email="v@anonymous.invalid", text=text, conversation_id=7, language="en", public=public
    )


async def test_public_visitor_cannot_look_up_orders():
    calls = []
    result = await run(public_handler(FakeSession(conv(status="open")), calls), "where is my order #12345", public=True)
    assert "lookup_order_status" not in calls
    assert calls and calls[0][0] == "handoff"
    assert "escalated" in result["content"]


async def test_public_visitor_cannot_add_to_cart():
    calls = []
    result = await run(public_handler(FakeSession(conv(status="open")), calls), "I want to buy this", public=True)
    assert "add_to_cart" not in calls
    assert calls[0][0] == "handoff"
    assert "escalated" in result["content"]


async def test_owner_chat_still_looks_up_orders_and_carts():
    calls = []
    handler = public_handler(FakeSession(conv(status="open")), calls)
    assert (await run(handler, "where is my order #12345", public=False))["content"] == "ORDER DATA"
    assert (await run(handler, "I want to buy this", public=False))["content"] == "CART DONE"
    assert calls == ["lookup_order_status", "add_to_cart"]


async def test_public_greeting_and_product_questions_still_work():
    calls = []
    handler = public_handler(FakeSession(conv(status="open")), calls)
    greeting = await run(handler, "hello", public=True)
    assert greeting["intent"] == "greeting" and not calls
