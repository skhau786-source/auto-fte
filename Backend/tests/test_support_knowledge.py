# ═══════════════════════════════════════════════════════════════
# tests / test_support_knowledge.py
#
# PURPOSE: customer_support ka knowledge-base (RAG) jawab —
#          LLM, "not covered" aur LLM-down fallback (no DB needed).
# ═══════════════════════════════════════════════════════════════

from src.sdk.exceptions import LLMError
from src.domains.agents.customer_support.handler import CustomerSupportHandler

HITS = [
    {
        "id": 1,
        "document_id": 1,
        "document_title": "Shipping policy",
        "content": "Standard delivery takes 3-5 business days. Shipping is free over 5000 PKR.",
        "similarity_score": 0.6,
    }
]


class FakeLLM:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.prompts = reply, error, []

    async def generate(self, prompt, system=""):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.reply


def make(llm) -> CustomerSupportHandler:
    return CustomerSupportHandler(db=None, llm_client=llm)


async def test_llm_answer_uses_passages_in_prompt():
    llm = FakeLLM(reply="It takes 3-5 business days.")
    answer = await make(llm).answer_from_knowledge("how long is shipping", "en", HITS)
    assert answer == "It takes 3-5 business days."
    assert "Standard delivery takes 3-5 business days" in llm.prompts[0]
    assert "how long is shipping" in llm.prompts[0]


async def test_not_covered_returns_empty_so_caller_can_fall_back():
    llm = FakeLLM(reply="NOT_COVERED")
    assert await make(llm).answer_from_knowledge("do you sell cars", "en", HITS) == ""


async def test_llm_error_falls_back_to_best_passage():
    llm = FakeLLM(error=LLMError("GEMINI_API_KEY is empty"))
    answer = await make(llm).answer_from_knowledge("shipping time", "en", HITS)
    assert answer.startswith("Here is what our store information says:")
    assert "3-5 business days" in answer


async def test_extractive_fallback_roman_urdu_intro():
    llm = FakeLLM(error=LLMError("down"))
    answer = await make(llm).answer_from_knowledge("shipping", "roman_urdu", HITS)
    assert answer.startswith("Hamari store information ke mutabiq:")


async def test_no_hits_returns_empty_without_calling_llm():
    llm = FakeLLM(reply="should not be used")
    assert await make(llm).answer_from_knowledge("anything", "en", []) == ""
    assert llm.prompts == []


import pytest


@pytest.mark.parametrize(
    "text",
    [
        "what is your return policy",
        "What is your refund policy?",
        "How long do refunds take?",
        "Can you tell me about your refund policy",
        "do you offer refunds?",
        "kya refund policy hai",
    ],
)
def test_policy_questions_are_answerable(text):
    assert make(FakeLLM())._is_policy_question(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "I want a refund",
        "refund my order #1234",
        "I need my money back",
        "mujhe refund chahiye",
        "cancel my order",
        "can I cancel my order?",
        "this is a scam",
        "I will sue you, what is your refund policy?",
        "what is your return policy, I want to talk to human",
        "refund",
        "hello there",
    ],
)
def test_actions_and_hard_keywords_still_escalate(text):
    assert make(FakeLLM())._is_policy_question(text) is False


async def test_try_policy_answer_uses_knowledge_base():
    handler = make(FakeLLM(error=LLMError("down")))
    refund_hits = [{**HITS[0], "document_title": "Returns", "content": "Returns are accepted within 30 days."}]

    async def fake_hits(store_id, query):
        return refund_hits

    handler._knowledge_hits = fake_hits
    answer = await handler._try_policy_answer(1, "what is your return policy", "en")
    assert "Returns are accepted within 30 days." in answer


async def test_try_policy_answer_empty_when_kb_has_nothing_or_not_policy():
    handler = make(FakeLLM(reply="x"))

    async def no_hits(store_id, query):
        return []

    handler._knowledge_hits = no_hits
    assert await handler._try_policy_answer(1, "what is your return policy", "en") == ""
    assert await handler._try_policy_answer(1, "I want a refund", "en") == ""


def test_trim_passage_cuts_at_sentence_boundary():
    text = "First sentence here. " * 60
    trimmed = CustomerSupportHandler._trim_passage(text, limit=100)
    assert len(trimmed) <= 105
    assert trimmed.endswith("…")
    assert "First sentence here." in trimmed


def test_format_passages_includes_titles():
    out = CustomerSupportHandler._format_passages(HITS)
    assert out.startswith("[Shipping policy]")
