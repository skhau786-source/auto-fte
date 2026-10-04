# ═══════════════════════════════════════════════════════════════
# agents / customer_support / handler.py
#
# PURPOSE: Business logic for Customer Support Agent.
#          Handles RAG product QA, order lookup, cart ops, and human handoff.
# ═══════════════════════════════════════════════════════════════

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.sdk.models.base import Store, Product, Variant, Order
from src.sdk.models.support import Conversation, Message, HandoffLog
from src.sdk.events import Event, SupportTicketEvent
from src.sdk.exceptions import LLMError
from src.sdk.llm.client import LLMClient
from src.sdk.llm.prompts import SUPPORT_QA_PROMPT

from src.domains.chatbot.rag_service import search_store_knowledge
from src.domains.agents.customer_support.config import get_settings
from src.domains.agents.customer_support.rules import (
    Intent,
    classify_intent,
    detect_language,
    format_product_answer,
    build_rag_context,
)
from src.domains.agents.customer_support.shopify_storefront_client import ShopifyStorefrontClient

logger = logging.getLogger(__name__)

# Knowledge base se jawab: LLM sirf diye hue passages se bole, warna saaf bata de.
KNOWLEDGE_QA_PROMPT = """
Answer the customer's question using ONLY the store information below.
If the information does not answer the question, reply exactly: NOT_COVERED
Do not invent policies, prices, dates or contact details.
Reply in this language: {language} (en = English, roman_urdu = Roman Urdu, urdu = Urdu).

Question: {query}

Store information:
{passages}

Be concise and friendly.
"""

KNOWLEDGE_NOT_COVERED = "NOT_COVERED"


class CustomerSupportHandler:
    """Core handler for customer chat and support actions."""

    def __init__(
        self,
        db: AsyncSession,
        llm_client: Optional[LLMClient] = None,
        event_bus=None,
        storefront_client: Optional[ShopifyStorefrontClient] = None,
    ):
        self.db = db
        self.settings = get_settings()
        self.llm = llm_client or LLMClient(api_key=self.settings.LLM_API_KEY)
        self.event_bus = event_bus
        self.storefront = storefront_client

    async def process_message(
        self,
        store_id: int,
        customer_email: str,
        text: str,
        conversation_id: Optional[int] = None,
        language: str = "",
    ) -> dict:
        """Main chat entry point: ingest user message, route intent, produce reply."""
        lang = language or detect_language(text)

        # 1. Get or create Conversation
        conversation = None
        if conversation_id:
            res = await self.db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conversation = res.scalar_one_or_none()

        if not conversation:
            conversation = Conversation(
                store_id=store_id,
                customer_email=customer_email or "guest@customer.com",
                status="open",
            )
            self.db.add(conversation)
            await self.db.flush()

        # 2. Add customer message
        cust_msg = Message(
            conversation_id=conversation.id,
            role="customer",
            content=text,
        )
        self.db.add(cust_msg)
        await self.db.flush()

        # 3. Classify intent
        intent = classify_intent(
            text,
            handoff_keywords=self.settings.HANDOFF_KEYWORDS,
            out_of_scope_keywords=self.settings.OUT_OF_SCOPE_KEYWORDS,
        )

        reply_content = ""

        # 4. Route intent
        if intent == Intent.OUT_OF_SCOPE:
            await self.handoff_to_human(conversation.id, reason=f"Out of scope keyword in: '{text}'")
            reply_content = (
                "Main ne aapki request human support team ko forward kar di hai. Ek agent jald aap se contact karega."
                if lang in ("roman_urdu", "urdu")
                else "I have escalated your request to our human support team. A representative will get back to you shortly."
            )

        elif intent == Intent.ORDER_STATUS:
            reply_content = ""
            # "delivery"/"tracking" jaise alfaz general policy sawalon mein bhi aate hain
            # ("cash on delivery?"). Order number/email na ho to pehle knowledge base dekho.
            if not (re.search(r"#?\d{3,8}", text) or re.search(r"[\w\.-]+@[\w\.-]+", text)):
                hits = await self._knowledge_hits(store_id, text)
                reply_content = await self.answer_from_knowledge(text, lang, hits) if hits else ""
            if not reply_content:
                reply_content = await self.lookup_order_status(store_id, text, lang)

        elif intent == Intent.CART_ADD:
            reply_content = await self.add_to_cart(store_id, conversation.id, text, lang)

        elif intent in (Intent.CART_REMOVE, Intent.CART_UPDATE):
            reply_content = (
                "Cart remove/update is not available yet. A support agent can help you with this request."
                if lang not in ("roman_urdu", "urdu")
                else "Cart se item remove/update karna abhi available nahi hai. Support agent aapki madad kar sakta hai."
            )

        elif intent == Intent.PRODUCT_QUESTION:
            # Catalog se jawab; owner ki knowledge base ke passages FAQ ke taur par saath jaate hain
            hits = await self._knowledge_hits(store_id, text)
            reply_content = await self.answer_product_question(
                store_id, text, lang, knowledge_hits=hits
            )

        elif intent == Intent.GREETING:
            reply_content = (
                "Assalam-o-Alaikum! Main aapki kya madad kar sakta hoon? Aap kisi product ya order ke baray me pooch saktay hain."
                if lang in ("roman_urdu", "urdu")
                else "Hello! Welcome to our store. How can I help you today? Feel free to ask about products, stock, or your order status."
            )

        else:  # FALLBACK
            # 1. Owner ki knowledge base (policies, FAQs) se jawab
            hits = await self._knowledge_hits(store_id, text)
            reply_content = await self.answer_from_knowledge(text, lang, hits) if hits else ""

            # 2. Warna product question, warna generic fallback
            if not reply_content:
                reply_content = await self.answer_product_question(store_id, text, lang)
            if not reply_content or "not found" in reply_content.lower() or "nahi mila" in reply_content.lower():
                reply_content = (
                    "Aapka sawal samajh nahi aya. Kya aap product ka naam ya order number bata saktay hain?"
                    if lang in ("roman_urdu", "urdu")
                    else "I'm not quite sure I understood. Could you please specify a product name or your order number?"
                )

        # 5. Add bot message
        bot_msg = Message(
            conversation_id=conversation.id,
            role="agent_bot",
            content=reply_content,
        )
        self.db.add(bot_msg)
        await self.db.flush()

        return {
            "conversation_id": conversation.id,
            "message_id": bot_msg.id,
            "role": "agent_bot",
            "content": reply_content,
            "intent": intent.value,
            "language": lang,
        }

    # ─── Knowledge base (RAG) ───────────────────────────────────

    async def _knowledge_hits(self, store_id: int, query: str) -> list[dict]:
        """Store owner ki knowledge base se relevant passages. Fail hone par chat na toote."""
        if not self.settings.KB_ENABLED:
            return []
        try:
            return await search_store_knowledge(
                self.db,
                store_id,
                query,
                top_k=self.settings.KB_TOP_K,
                min_score=self.settings.KB_MIN_SCORE,
            )
        except Exception as e:
            logger.warning(f"Knowledge base lookup failed (store={store_id}): {e}")
            return []

    @staticmethod
    def _format_passages(hits: list[dict]) -> str:
        return "\n\n".join(f"[{h['document_title']}]\n{h['content']}" for h in hits)

    @staticmethod
    def _trim_passage(text: str, limit: int = 700) -> str:
        if len(text) <= limit:
            return text
        cut = text[:limit]
        end = max(cut.rfind(". "), cut.rfind("\n"))
        return (cut[: end + 1] if end > limit // 3 else cut).strip() + " …"

    async def answer_from_knowledge(self, query: str, language: str, hits: list[dict]) -> str:
        """Knowledge base passages se jawab. "" return hota hai agar passages sawal ka jawab nahi dete.

        LLM ho to sirf passages se jawab banata hai; LLM na ho (ya fail ho) to
        sabse relevant passage seedha dikhata hai (kuch invent nahi hota).
        """
        if not hits:
            return ""
        prompt = KNOWLEDGE_QA_PROMPT.format(
            language=language or "en", query=query, passages=self._format_passages(hits)
        )
        try:
            answer = (await self.llm.generate(
                prompt, system="You are a helpful customer support agent for an online store."
            )).strip()
            if not answer or KNOWLEDGE_NOT_COVERED in answer:
                return ""
            return answer
        except Exception as e:
            logger.info(f"LLM unavailable for knowledge answer, using extractive fallback: {e}")
            best = self._trim_passage(hits[0]["content"])
            intro = (
                "Hamari store information ke mutabiq:"
                if language in ("roman_urdu", "urdu")
                else "Here is what our store information says:"
            )
            return f"{intro}\n\n{best}"

    async def answer_product_question(
        self,
        store_id: int,
        query: str,
        language: str = "en",
        knowledge_hits: Optional[list[dict]] = None,
    ) -> str:
        """Answer product questions using live DB catalog (never guessed).

        knowledge_hits: owner ki knowledge base ke passages. Koi product match na ho
        to inhi se jawab diya jata hai (arbitrary pehla product dikhane se behtar);
        warna FAQ ke taur par LLM prompt mein jaate hain.
        """
        # Fetch active products for this store
        res = await self.db.execute(
            select(Product).where(Product.store_id == store_id)
        )
        products = res.scalars().all()

        if not products:
            return (
                "Abhi store par koi products available nahi hain."
                if language in ("roman_urdu", "urdu")
                else "There are currently no products available in the store catalog."
            )

        # Score matching products by token overlap
        tokens = set(re.findall(r"\b\w{3,}\b", query.lower()))
        scored = []
        for p in products:
            title_tokens = set(re.findall(r"\b\w{3,}\b", (p.title or "").lower()))
            desc_tokens = set(re.findall(r"\b\w{3,}\b", (p.description or "").lower()))
            score = len(tokens & title_tokens) * 3 + len(tokens & desc_tokens)
            if score > 0 or not tokens:
                # Fetch variants
                var_res = await self.db.execute(
                    select(Variant).where(Variant.product_id == p.id)
                )
                variants = var_res.scalars().all()
                scored.append({"product": p, "variants": variants, "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        top_matches = scored[: self.settings.MAX_RAG_PRODUCTS]

        if not top_matches and knowledge_hits:
            answer = await self.answer_from_knowledge(query, language, knowledge_hits)
            if answer:
                return answer

        if not top_matches:
            # Fallback to the first product if general inquiry
            p = products[0]
            var_res = await self.db.execute(
                select(Variant).where(Variant.product_id == p.id)
            )
            top_matches = [{"product": p, "variants": var_res.scalars().all(), "score": 0}]

        # Try LLM RAG with prompt
        rag_context = build_rag_context(top_matches)
        prompt = SUPPORT_QA_PROMPT.format(query=query, context=rag_context, faq_data=self._format_passages(knowledge_hits or []))
        try:
            return await self.llm.generate(prompt, system="You are a helpful customer support agent.")
        except (NotImplementedError, LLMError):
            # LLM nahi (ya key khaali) — deterministic fallback using live catalog price/stock
            best = top_matches[0]
            prod = best["product"]
            variants = best["variants"]
            price = float(variants[0].price) if variants else 0.0
            stock = variants[0].inventory_quantity if variants else 0
            return format_product_answer(
                title=prod.title,
                price=price,
                inventory_quantity=stock,
                language=language,
                description=prod.description or "",
            )

    async def lookup_order_status(self, store_id: int, text: str, language: str = "en") -> str:
        """Lookup order status using local synced orders table."""
        # Find order number (digits or #1234) or email
        order_match = re.search(r"#?(\d{3,8})", text)
        email_match = re.search(r"[\w\.-]+@[\w\.-]+", text)

        query = select(Order).where(Order.store_id == store_id)

        if order_match:
            order_num = order_match.group(1)
            query = query.where(
                or_(
                    Order.order_number == order_num,
                    Order.platform_order_id.contains(order_num),
                )
            )
        elif email_match:
            query = query.where(Order.customer_email == email_match.group(0))
        else:
            return (
                "Order status check karne ke liye apna Order Number (e.g. #1001) ya Email provide karein."
                if language in ("roman_urdu", "urdu")
                else "Please provide your Order Number (e.g. #1001) or email address to check the status."
            )

        res = await self.db.execute(query.limit(1))
        order = res.scalar_one_or_none()

        if not order:
            return (
                f"Is detail se koi order nahi mila. Barah-e-karam apna sahih order number check karein."
                if language in ("roman_urdu", "urdu")
                else f"No order found matching your details. Please double-check your order number."
            )

        f_status = order.fulfillment_status or "Processing"
        pay_status = order.financial_status or "Paid"
        total = float(order.total_price) if order.total_price else 0.0

        if language in ("roman_urdu", "urdu"):
            return f"Aapka Order **#{order.order_number or order.platform_order_id}** (Total: ${total:.2f}) abhi **{f_status}** stage me hai. Payment status: **{pay_status}**."

        return f"Order **#{order.order_number or order.platform_order_id}** (Total: ${total:.2f}) status is currently **{f_status}**. Payment: **{pay_status}**."

    async def add_to_cart(
        self,
        store_id: int,
        conversation_id: int,
        text: str,
        language: str = "en",
    ) -> str:
        """Handle add to cart via Storefront client with dev-mode."""
        # Find store
        res = await self.db.execute(select(Store).where(Store.id == store_id))
        store = res.scalar_one_or_none()
        shop_domain = store.shop_domain if store else "demo.myshopify.com"

        client = self.storefront or ShopifyStorefrontClient(
            shop_domain=shop_domain,
            access_token=self.settings.STOREFRONT_ACCESS_TOKEN,
        )

        # Resolve variant
        var_res = await self.db.execute(
            select(Variant).join(Product).where(Product.store_id == store_id).limit(1)
        )
        variant = var_res.scalar_one_or_none()

        if not variant:
            await self.handoff_to_human(conversation_id, reason=f"Could not resolve product for cart: {text}")
            return (
                "Main product pehchan nahi saka. Ek human agent aapki madad karega."
                if language in ("roman_urdu", "urdu")
                else "I couldn't identify the exact product variant to add. I've alerted our team to assist you."
            )

        try:
            cart_resp = await client.create_cart([
                {"merchandiseId": f"gid://shopify/ProductVariant/{variant.platform_variant_id}", "quantity": 1}
            ])
            return (
                f"Item cart me add ho gaya hai! Checkout link: {cart_resp.get('checkout_url')}"
                if language in ("roman_urdu", "urdu")
                else f"Item has been added to your cart! You can complete checkout here: {cart_resp.get('checkout_url')}"
            )
        except Exception as e:
            logger.error(f"Cart operation error: {e}")
            await self.handoff_to_human(conversation_id, reason=f"Cart API error: {str(e)}")
            return "Cart service is temporarily unavailable. A support agent will assist you shortly."

    async def handoff_to_human(self, conversation_id: int, reason: str) -> None:
        """Escalate conversation to human agent."""
        res = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = res.scalar_one_or_none()
        if not conv:
            return

        conv.status = "handoff"
        handoff = HandoffLog(
            conversation_id=conversation_id,
            reason=reason,
            assigned_to="human_queue",
        )
        self.db.add(handoff)
        await self.db.flush()

        # Publish event to bus if available
        if self.event_bus:
            try:
                evt = SupportTicketEvent(
                    source="customer_support",
                    payload={
                        "conversation_id": conversation_id,
                        "store_id": conv.store_id,
                        "customer_email": conv.customer_email,
                        "query": reason,
                        "handoff_id": handoff.id,
                    },
                )
                await self.event_bus.publish("events", evt.model_dump())
            except Exception as e:
                logger.warning(f"Failed to publish support ticket event: {e}")

    async def human_reply(self, conversation_id: int, text: str) -> Message:
        """Human agent adds a reply to an escalated conversation."""
        res = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = res.scalar_one_or_none()
        if not conv:
            raise ValueError(f"Conversation {conversation_id} not found")

        conv.status = "open"  # Re-opened/active
        msg = Message(
            conversation_id=conversation_id,
            role="agent_human",
            content=text,
        )
        self.db.add(msg)
        await self.db.flush()
        return msg

    async def close_conversation(self, conversation_id: int) -> Conversation:
        """Close conversation."""
        res = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = res.scalar_one_or_none()
        if not conv:
            raise ValueError(f"Conversation {conversation_id} not found")

        conv.status = "closed"
        conv.closed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return conv

    async def list_conversations(self, store_id: int, status: Optional[str] = None) -> list[Conversation]:
        query = select(Conversation).where(Conversation.store_id == store_id)
        if status:
            query = query.where(Conversation.status == status)
        res = await self.db.execute(query.order_by(Conversation.created_at.desc()))
        return list(res.scalars().all())

    async def get_conversation(self, conversation_id: int) -> Optional[dict]:
        res = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = res.scalar_one_or_none()
        if not conv:
            return None

        msg_res = await self.db.execute(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
        )
        messages = msg_res.scalars().all()

        return {
            "id": conv.id,
            "store_id": conv.store_id,
            "customer_email": conv.customer_email,
            "status": conv.status,
            "created_at": conv.created_at,
            "closed_at": conv.closed_at,
            "messages": [
                {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
                for m in messages
            ],
        }

    async def list_handoffs(self, store_id: Optional[int] = None, limit: int = 50) -> list[HandoffLog]:
        query = select(HandoffLog).order_by(HandoffLog.created_at.desc()).limit(limit)
        res = await self.db.execute(query)
        return list(res.scalars().all())
