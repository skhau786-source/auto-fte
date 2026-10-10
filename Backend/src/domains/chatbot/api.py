# =============================================================
# domains / chatbot / api.py
#
# PURPOSE: Backend adapters for the two packaged chatbot widgets.
#
# FREE:
#   - Guest users: general knowledge / educational assistant only.
#   - Authenticated users: connected-store read-only support.
#
# PRO:
#   - Authenticated users only.
#   - Support + action capabilities exposed by the support handler.
#
# =============================================================

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.sdk.database import get_db
from src.sdk.models.base import Store
from src.sdk.models.support import Conversation, Message
from src.domains.auth.models import User
from src.domains.auth.service import (
    get_current_user,
    get_optional_current_user,
)
from src.domains.agents.customer_support.config import (
    get_settings as get_support_settings,
)
from src.domains.agents.customer_support.handler import (
    CustomerSupportHandler,
)
from src.domains.agents.customer_support.rules import (
    Intent,
    classify_intent,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chatbots"])


# =============================================================
# REQUEST / RESPONSE MODELS
# =============================================================

class ChatbotRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=4000,
    )

    preferred_language: Optional[str] = None

    store_id: Optional[int] = None

    conversation_id: Optional[int] = None

    customer_email: Optional[str] = None


class ChatbotResponse(BaseModel):
    answer: str
    message: str

    conversation_id: int
    message_id: int

    intent: str
    language: str

    plan: Literal["free", "pro"]

    mode: Literal["read_only", "agent"]

    # Handoff: bot chup hai (answer khali) — widget kuch na dikhaye; polling se owner ka reply aayega
    silent: bool = False
    conversation_status: str = "open"


# =============================================================
# STORE RESOLUTION
# =============================================================

async def _resolve_store(
    body: ChatbotRequest,
    current_user: User,
    db: AsyncSession,
) -> Store:
    """
    Resolve only a store owned by the authenticated user.
    """

    query = select(Store).where(
        Store.user_id == current_user.id,
        Store.is_active.is_(True),
    )

    if body.store_id is not None:
        query = query.where(
            Store.id == body.store_id
        )
    else:
        query = query.order_by(
            Store.created_at.asc()
        )

    result = await db.execute(
        query.limit(1)
    )

    store = result.scalar_one_or_none()

    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No active store is connected to this account. "
                "Connect a store first."
            ),
        )

    return store


# =============================================================
# AUTHENTICATED CHAT
# =============================================================

async def _chat(
    body: ChatbotRequest,
    plan: Literal["free", "pro"],
    db: AsyncSession,
    current_user: User,
) -> ChatbotResponse:
    """
    Handle authenticated Free and Pro chatbot requests.
    """

    store = await _resolve_store(
        body,
        current_user,
        db,
    )

    support_settings = get_support_settings()

    # ---------------------------------------------------------
    # INTENT CLASSIFICATION
    # ---------------------------------------------------------

    intent = classify_intent(
        body.query,
        handoff_keywords=support_settings.HANDOFF_KEYWORDS,
        out_of_scope_keywords=support_settings.OUT_OF_SCOPE_KEYWORDS,
    )

    # ---------------------------------------------------------
    # FREE PLAN = READ ONLY
    #
    # Never allow the Free client to trigger store actions.
    # This restriction is enforced server-side.
    # ---------------------------------------------------------

    if plan == "free" and intent in {
        Intent.CART_ADD,
        Intent.CART_REMOVE,
        Intent.CART_UPDATE,
    }:
        lang = (
            body.preferred_language
            or "en"
        )

        if lang == "urdu":
            message = (
                "Free Plan read-only hai. "
                "Store actions ke liye Pro Agent use karein."
            )

        elif lang == "roman_urdu":
            message = (
                "Free Plan read-only hai. "
                "Store actions ke liye Pro Agent use karein."
            )

        else:
            message = (
                "The Free Plan chatbot is read-only. "
                "Use the Pro Agent for store actions."
            )

        return ChatbotResponse(
            answer=message,
            message=message,
            conversation_id=(
                body.conversation_id or 0
            ),
            message_id=0,
            intent=intent.value,
            language=lang,
            plan="free",
            mode="read_only",
        )

    # ---------------------------------------------------------
    # CUSTOMER SUPPORT HANDLER
    # ---------------------------------------------------------

    handler = CustomerSupportHandler(db)

    result = await handler.process_message(
        store_id=store.id,
        customer_email=(
            body.customer_email
            or current_user.email
        ),
        text=body.query,
        conversation_id=body.conversation_id,
        language=body.preferred_language or "",
        authenticated_email=current_user.email,
    )

    await db.commit()

    answer = (
        result.get("content")
        or result.get("answer")
        or result.get("message")
        or ""
    )

    return ChatbotResponse(
        answer=answer,
        message=answer,
        conversation_id=int(
            result["conversation_id"]
        ),
        message_id=int(
            result["message_id"]
        ),
        intent=result.get(
            "intent",
            intent.value,
        ),
        language=result.get(
            "language",
            body.preferred_language or "en",
        ),
        plan=plan,
        mode=(
            "read_only"
            if plan == "free"
            else "agent"
        ),
        silent=bool(result.get("silent", False)),
        conversation_status=result.get("conversation_status", "open"),
    )


# =============================================================
# FREE CHATBOT
# =============================================================

@router.post(
    "/chatbot/query",
    response_model=ChatbotResponse,
)
async def free_chatbot_query(
    body: ChatbotRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(
        get_optional_current_user
    ),
):
    """
    Free chatbot behavior:

    Guest:
        - General knowledge
        - Educational questions
        - Public information
        - No private store/account information

    Authenticated:
        - Connected store
        - Read-only support
        - No store actions
    """

    # =========================================================
    # GUEST MODE
    # =========================================================

    if current_user is None:

        support_settings = get_support_settings()

        from src.sdk.llm.client import LLMClient

        llm = LLMClient(
            api_key=support_settings.LLM_API_KEY,
            model=support_settings.LLM_MODEL,
        )

        language = (
            body.preferred_language
            or "en"
        )

        # -----------------------------------------------------
        # LANGUAGE
        # -----------------------------------------------------

        if language == "urdu":

            language_instruction = """
Answer in natural Urdu.
Use clear, simple Urdu.
"""

        elif language == "roman_urdu":

            language_instruction = """
Answer in natural Roman Urdu.
Do not switch to English unless a technical term
or proper noun is necessary.
"""

        else:

            language_instruction = """
Answer in clear, natural English.
"""

        # -----------------------------------------------------
        # GUEST SYSTEM PROMPT
        # -----------------------------------------------------
        #
        # IMPORTANT:
        # General/public questions MUST be answered normally.
        # Login is required only for private/account-specific data.
        # -----------------------------------------------------

        system_prompt = f"""
You are the Digital FTE Free Plan AI Assistant.

Your primary job is to answer general knowledge,
educational, technology, programming, AI, business,
and e-commerce questions helpfully and accurately.

The user may be completely logged out.
Being logged out does NOT prevent you from answering
general or public questions.

IMPORTANT RULES:

1. ANSWER GENERAL QUESTIONS NORMALLY

Examples of questions that MUST be answered without login:

- What is Digital FTE?
- What is artificial intelligence?
- What is Shopify?
- What is e-commerce?
- How does Python work?
- What is an API?
- What is machine learning?
- Explain PostgreSQL.
- What is SaaS?

"Digital FTE" is a general concept.
It is NOT private store information.
Never ask the user to log in just because the question
mentions Digital FTE, Shopify, WooCommerce, AI,
e-commerce, programming, or another public technology.

2. DO NOT INVENT PRIVATE DATA

You do not have access to a guest user's private:
- store data
- products
- orders
- inventory
- customers
- account information
- connected platform information

Never invent, guess, or pretend to know that information.

3. LOGIN IS ONLY REQUIRED FOR PRIVATE DATA

Ask the user to log in ONLY when they request
information specific to their own account or connected store.

Examples:

- Show my Shopify orders.
- What products are in my store?
- How many items are in my inventory?
- Show my customers.
- What is my store's sales data?
- Show my connected store information.

For these requests, politely explain that
the user must log in to access private store/account data.

4. PUBLIC INFORMATION IS NOT PRIVATE INFORMATION

You may answer public/general questions about:
- Shopify
- WooCommerce
- BigCommerce
- Amazon
- Daraz
- APIs
- payment systems
- e-commerce
- business
- technology
- AI
- programming
- software

Do not confuse a question about a platform with
a request for that user's private platform data.

For example:

"How does Shopify work?"
-> Answer normally.

"What products are in my Shopify store?"
-> Require login.

5. DO NOT MENTION LOGIN UNLESS NECESSARY

For a normal general-knowledge question, simply answer it.
Do not add unnecessary login warnings.

6. DO NOT CLAIM TO ACCESS A USER'S STORE

As a guest, you do not have store access.

7. BE HELPFUL

Give a direct answer first.
Use examples when useful.
Avoid unnecessary refusal language.

{language_instruction}
"""

        # -----------------------------------------------------
        # GENERATE GENERAL KNOWLEDGE ANSWER
        # -----------------------------------------------------

        answer = await llm.generate(
            body.query,
            system=system_prompt,
        )

        return ChatbotResponse(
            answer=answer,
            message=answer,
            conversation_id=body.conversation_id or 0,
            message_id=0,
            intent="general_knowledge",
            language=language,
            plan="free",
            mode="read_only",
        )

    # =========================================================
    # AUTHENTICATED FREE MODE
    # =========================================================

    return await _chat(
        body,
        "free",
        db,
        current_user,
    )


# =============================================================
# PRO AI AGENT
# =============================================================

@router.post(
    "/agent/query",
    response_model=ChatbotResponse,
)
async def pro_agent_query(
    body: ChatbotRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    """
    Pro chatbot:
    authenticated support chat with available
    store/action capabilities.
    """

    return await _chat(
        body,
        "pro",
        db,
        current_user,
    )


# =============================================================
# SUPPORT TEAM REPLIES (widget polling)
# =============================================================

@router.get("/chatbot/conversations/{conversation_id}/messages")
async def conversation_support_replies(
    conversation_id: int,
    after_id: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Widget polling: support team (owner inbox) ke naye replies.

    Sirf role=agent_human wale messages jinki id after_id se bari ho —
    customer aur bot ke messages widget khud dikhata hai. Sirf us user ko
    jiska yeh store hai; warna 404.
    """

    conv = (
        await db.execute(
            select(Conversation)
            .join(Store, Store.id == Conversation.store_id)
            .where(
                Conversation.id == conversation_id,
                Store.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()

    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    rows = (
        await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conv.id,
                Message.role == "agent_human",
                Message.id > after_id,
            )
            .order_by(Message.id)
            .limit(50)
        )
    ).scalars().all()

    return {
        "conversation_id": conv.id,
        "status": conv.status,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
            }
            for m in rows
        ],
    }