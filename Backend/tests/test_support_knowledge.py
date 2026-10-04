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


def test_trim_passage_cuts_at_sentence_boundary():
    text = "First sentence here. " * 60
    trimmed = CustomerSupportHandler._trim_passage(text, limit=100)
    assert len(trimmed) <= 105
    assert trimmed.endswith("…")
    assert "First sentence here." in trimmed


def test_format_passages_includes_titles():
    out = CustomerSupportHandler._format_passages(HITS)
    assert out.startswith("[Shipping policy]")
