# ═══════════════════════════════════════════════════════════════
# tests / test_support_handoff.py
#
# PURPOSE: Handoff ke dauran bot chup rehta hai (sirf ek dafa
#          "team jald jawab degi"), bot wapas aaye to jawab deta hai.
#          Fake DB session — koi database nahi chahiye.
# ═══════════════════════════════════════════════════════════════

from src.sdk.models.support import Conversation, Message
from src.domains.agents.customer_support.handler import (
    CustomerSupportHandler,
    HANDOFF_WAITING_MESSAGES,
)


class _One:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    """conversations query → conv; messages query → last_non_customer; add/flush record karta hai."""

    def __init__(self, conv, last_non_customer=None):
        self.conv, self.last, self.added = conv, last_non_customer, []

    async def execute(self, stmt):
        return _One(self.conv if "FROM conversations" in str(stmt) else self.last)

    def add(self, obj):
        if isinstance(obj, Message) and obj.id is None:
            obj.id = 1000 + len(self.added)
        self.added.append(obj)

    async def flush(self):
        pass


class ExplodingLLM:
    """Handoff mein LLM kabhi call nahi hona chahiye."""

    called = False

    async def generate(self, *args, **kwargs):
        ExplodingLLM.called = True
        raise AssertionError("LLM must not be called while a chat is in handoff")


def conv(status="handoff"):
    return Conversation(id=7, store_id=1, customer_email="c@example.com", status=status)


def msg(role, content, id=1):
    return Message(id=id, conversation_id=7, role=role, content=content)


def handler(session):
    ExplodingLLM.called = False
    return CustomerSupportHandler(db=session, llm_client=ExplodingLLM())


async def send(session, text, language="en", conversation_id=7):
    return await handler(session).process_message(
        store_id=1, customer_email="c@example.com", text=text, conversation_id=conversation_id, language=language
    )


async def test_first_message_after_escalation_gets_waiting_notice():
    session = FakeSession(conv(), msg("agent_bot", "I have escalated your request to our human support team."))
    result = await send(session, "hello? anyone there")
    assert result["content"] == HANDOFF_WAITING_MESSAGES["en"]
    assert result["silent"] is False
    assert result["conversation_status"] == "handoff"
    assert result["message_id"] > 0
    assert not ExplodingLLM.called
    roles = [m.role for m in session.added]
    assert roles == ["customer", "agent_bot"]  # customer ka message save + ek holding message


async def test_waiting_notice_is_roman_urdu_and_urdu_by_language():
    for lang in ("roman_urdu", "urdu"):
        session = FakeSession(conv(), msg("agent_bot", "escalated"))
        result = await send(session, "koi hai?", language=lang)
        assert result["content"] == HANDOFF_WAITING_MESSAGES[lang]


async def test_second_message_is_silent_after_notice():
    session = FakeSession(conv(), msg("agent_bot", HANDOFF_WAITING_MESSAGES["en"]))
    result = await send(session, "please hurry")
    assert result["silent"] is True
    assert result["content"] == ""
    assert result["message_id"] == 0
    assert [m.role for m in session.added] == ["customer"]  # sirf customer ka message save, bot ka koi nahi
    assert not ExplodingLLM.called


async def test_silent_even_if_notice_was_in_other_language():
    session = FakeSession(conv(), msg("agent_bot", HANDOFF_WAITING_MESSAGES["roman_urdu"]))
    result = await send(session, "any update?", language="en")
    assert result["silent"] is True


async def test_after_owner_reply_notice_is_sent_again_once():
    session = FakeSession(conv(), msg("agent_human", "Share your order number please"))
    result = await send(session, "it is 1234")
    assert result["content"] == HANDOFF_WAITING_MESSAGES["en"]
    assert not ExplodingLLM.called


async def test_policy_question_in_handoff_is_not_answered_by_bot():
    session = FakeSession(conv(), msg("agent_bot", HANDOFF_WAITING_MESSAGES["en"]))
    result = await send(session, "what is your return policy")
    assert result["silent"] is True
    assert result["content"] == ""
    assert not ExplodingLLM.called


async def test_after_hand_back_bot_answers_again():
    # status "open" (inbox se "Hand back to bot") → normal routing; greeting LLM ke bina jawab deta hai
    session = FakeSession(conv(status="open"))
    result = await send(session, "hello")
    assert result["silent"] is False
    assert result["intent"] == "greeting"
    assert result["conversation_status"] == "open"
    assert "Welcome" in result["content"]


async def test_customer_writing_in_resolved_chat_reopens_it():
    from datetime import datetime, timezone

    closed = conv(status="closed")
    closed.closed_at = datetime.now(timezone.utc)
    result = await send(FakeSession(closed), "hello")
    assert closed.status == "open" and closed.closed_at is None
    assert result["conversation_status"] == "open"
    assert result["silent"] is False
    assert "Welcome" in result["content"]


async def test_conversation_id_of_another_store_starts_a_new_conversation():
    # store filter ki wajah se query kuch nahi lautati → nayi conversation banti hai
    session = FakeSession(conv=None)

    async def fake_flush():
        for obj in session.added:
            if isinstance(obj, Conversation) and obj.id is None:
                obj.id = 55

    session.flush = fake_flush
    result = await send(session, "hello", conversation_id=7)
    assert result["conversation_id"] == 55
    created = [o for o in session.added if isinstance(o, Conversation)]
    assert len(created) == 1 and created[0].store_id == 1
