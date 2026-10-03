"""Support chat: intent rules (English + Roman Urdu) and the LLM fallback with a fake client."""

from types import SimpleNamespace

import pytest

from app.ai import llm_client
from app.ai.llm_client import LLMResponse, MockLLMClient
from app.support_chat import llm, nlu

STORE = SimpleNamespace(shopify_domain="demo.myshopify.com", id="s1", owner_id="o1")


# ── rules ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text,intent",
    [
        ("hello", "greeting"),
        ("Assalam o alaikum", "greeting"),
        ("canvas backpack price?", "price"),
        ("Canvas backpack ki qeemat kya hai", "price"),
        ("backpack kitne ka hai", "price"),
        ("is the canvas backpack in stock?", "stock"),
        ("kitne bache hain backpack", "stock"),
        ("where is my order 1234", "order"),
        ("mera parcel kahan hai", "order"),
        ("owner se baat karni hai", "handoff"),
        ("mujhe shikayat hai", "handoff"),
        ("shukriya", "thanks"),
    ],
)
def test_intents(text, intent):
    assert nlu.detect_intent(text) == intent


def test_language_detection():
    assert nlu.detect_language("backpack kitne ka hai") == "ur"
    assert nlu.detect_language("how much is the backpack") == "en"


def test_order_reference():
    assert nlu.extract_order_ref("order #5521 status") == "5521"
    assert nlu.extract_order_ref("mera parcel kahan hai") is None


# ── parse_reply ────────────────────────────────────────────────────────

def test_parse_plain_json():
    assert llm.parse_reply('{"reply": "Hi!", "handoff": false}') == ("Hi!", False)


def test_parse_fenced_json_with_handoff():
    raw = '```json\n{"reply": "I will ask the owner.", "handoff": true}\n```'
    assert llm.parse_reply(raw) == ("I will ask the owner.", True)


def test_parse_plain_text_is_used_as_reply():
    assert llm.parse_reply("Sure, we ship in 3-5 days.") == ("Sure, we ship in 3-5 days.", False)


@pytest.mark.parametrize("raw", ["", "   ", '{"reply": ', '{"nothing": 1}'])
def test_parse_unusable_returns_none(raw):
    assert llm.parse_reply(raw) is None


def test_context_lists_matches_catalog_and_faq():
    ctx = llm.build_context(["- Wool Beanie: price 24.00, 3 in stock"], ["Wool Beanie", "Tee"], ["[Shipping] 3-5 days"])
    assert "Wool Beanie: price 24.00" in ctx and "Shipping" in ctx and "Tee" in ctx
    assert "no matching product" in llm.build_context([], [], [])


# ── llm_answer with a fake client ──────────────────────────────────────

class FakeClient(MockLLMClient):
    provider_name = "fake"

    def __init__(self, content="", exc=None):
        super().__init__()
        self.content, self.exc, self.calls = content, exc, []

    async def chat(self, messages, model=None, max_tokens=1024, temperature=0.7):
        self.calls.append(messages)
        if self.exc:
            raise self.exc
        return LLMResponse(content=self.content, provider="fake", tokens_used=42)


@pytest.fixture
def patched(monkeypatch):
    async def products(db, store_id, message):
        return ["- Wool Beanie: price 24.00, 993 in stock"], ["Wool Beanie"]

    async def faq(db, store, message):
        return ["[Shipping policy] We ship in 3 to 5 working days."]

    monkeypatch.setattr(llm, "_product_lines", products)
    monkeypatch.setattr(llm, "_faq_chunks", faq)

    def install(client):
        llm_client.set_llm_client(client)
        return client

    yield install
    llm_client.reset_llm_client()


@pytest.mark.asyncio
async def test_no_key_means_no_llm(patched):
    patched(MockLLMClient())
    assert await llm.llm_answer(None, STORE, "do you ship?", []) is None


@pytest.mark.asyncio
async def test_reply_is_returned_and_prompt_is_grounded(patched):
    c = patched(FakeClient('{"reply": "Delivery takes 3 to 5 working days.", "handoff": false}'))
    history = [{"role": "customer", "text": "hi"}, {"role": "bot", "text": "Hello!"}]
    res = await llm.llm_answer(None, STORE, "kitne din mein delivery hoti hai", history)
    assert res == {"reply": "Delivery takes 3 to 5 working days.", "handoff": False}

    msgs = c.calls[0]
    assert [m.role for m in msgs] == ["system", "user", "assistant", "user"]
    assert "Wool Beanie: price 24.00" in msgs[0].content and "3 to 5 working days" in msgs[0].content
    assert "kitne din mein delivery hoti hai" not in msgs[0].content  # customer text never enters the system prompt
    assert msgs[-1].content == "kitne din mein delivery hoti hai"


@pytest.mark.asyncio
async def test_handoff_flag(patched):
    patched(FakeClient('{"reply": "I will pass this to the owner.", "handoff": true}'))
    res = await llm.llm_answer(None, STORE, "I want a refund now", [])
    assert res["handoff"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("client", [FakeClient(exc=TimeoutError("slow")), FakeClient(content="{broken")])
async def test_failures_fall_back_to_rules(patched, client):
    patched(client)
    assert await llm.llm_answer(None, STORE, "anything", []) is None


def test_per_session_rate_limit(monkeypatch):
    monkeypatch.setattr(llm.settings, "SUPPORT_CHAT_LLM_PER_SESSION_HOUR", 3, raising=False)
    llm._calls.clear()
    assert [llm.allow_call("a", now=t) for t in (0, 1, 2, 3)] == [True, True, True, False]
    assert llm.allow_call("b", now=3)                 # other sessions are unaffected
    assert llm.allow_call("a", now=3601)              # window slides after an hour
    llm._calls.clear()


@pytest.mark.asyncio
async def test_rate_limited_session_falls_back_to_rules(patched, monkeypatch):
    patched(FakeClient('{"reply": "x", "handoff": false}'))
    monkeypatch.setattr(llm.settings, "SUPPORT_CHAT_LLM_PER_SESSION_HOUR", 1, raising=False)
    llm._calls.clear()
    assert await llm.llm_answer(None, STORE, "q1", [], "sess") is not None
    assert await llm.llm_answer(None, STORE, "q2", [], "sess") is None
    llm._calls.clear()


@pytest.mark.asyncio
async def test_disabled_by_setting(patched, monkeypatch):
    patched(FakeClient('{"reply": "x", "handoff": false}'))
    monkeypatch.setattr(llm.settings, "SUPPORT_CHAT_LLM_ENABLED", False, raising=False)
    assert await llm.llm_answer(None, STORE, "hello there", []) is None
