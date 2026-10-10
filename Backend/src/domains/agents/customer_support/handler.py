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

from src.domains.chatbot.rag_service import STOPWORDS, list_store_knowledge_topics, search_store_knowledge
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

# Handoff ke dauran bot chup rehta hai; sirf ek dafa yeh bolta hai (zabaan ke hisaab se).
HANDOFF_WAITING_MESSAGES = {
    "en": "Our team will get back to you shortly.",
    "roman_urdu": "Hamari team jald aap ko jawab degi.",
    "urdu": "ہماری ٹیم جلد آپ کو جواب دے گی۔",
}


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
        public: bool = False,
        authenticated_email: Optional[str] = None,
    ) -> dict:
        """Main chat entry point: ingest user message, route intent, produce reply.

        public=True: anjaan website visitor. Sirf sawal-jawab, product price/stock aur policy
        (knowledge base). Order lookup (customer data) aur cart actions band — woh human ko jate hain.

        authenticated_email: logged-in user ki email (auth token se, chat text se kabhi nahi);
        order lookup sirf isi email ke orders dikhata hai.
        """
        lang = language or detect_language(text)

        # 1. Get or create Conversation
        conversation = None
        if conversation_id:
            # store_id bhi match ho: kisi aur store ki conversation id par message inject nahi hota
            res = await self.db.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id, Conversation.store_id == store_id
                )
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

        # Resolved (closed) chat mein customer dobara likhe → chat dobara open ho jaye
        # (warna bot jawab deta rehta lekin chat "closed" dikhti, inbox mein kahin nazar na aati).
        if conversation.status == "closed":
            conversation.status = "open"
            conversation.closed_at = None

        # 2. Add customer message
        cust_msg = Message(
            conversation_id=conversation.id,
            role="customer",
            content=text,
        )
        self.db.add(cust_msg)
        await self.db.flush()

        # 2b. Handoff mein ho to bot chup: na intent routing, na LLM/knowledge base.
        # Message owner ke inbox ke liye save ho chuka hai.
        if conversation.status == "handoff":
            return await self._handoff_waiting_reply(conversation, lang)

        # 3. Classify intent
        intent = classify_intent(
            text,
            handoff_keywords=self.settings.HANDOFF_KEYWORDS,
            out_of_scope_keywords=self.settings.OUT_OF_SCOPE_KEYWORDS,
        )

        reply_content = ""

        # 4. Route intent
        if intent == Intent.OUT_OF_SCOPE:
            # "What is your return policy?" jaise info sawal knowledge base se; asli refund/cancel
            # requests aur hard keywords (scam, legal, ...) hamesha human ko jaate hain.
            reply_content = await self._try_policy_answer(store_id, text, lang)
            if not reply_content:
                reply_content = await self._escalate(conversation.id, f"Out of scope keyword in: '{text}'", lang)

        elif intent == Intent.ORDER_STATUS:
            reply_content = ""
            # "delivery"/"tracking" jaise alfaz general policy sawalon mein bhi aate hain
            # ("cash on delivery?"). Order number/email na ho to pehle knowledge base dekho.
            if not (re.search(r"#?\d{3,8}", text) or re.search(r"[\w\.-]+@[\w\.-]+", text)):
                hits = await self._knowledge_hits(store_id, text)
                reply_content = await self.answer_from_knowledge(text, lang, hits) if hits else ""
            if not reply_content:
                if public:
                    # Order lookup customer data dikhata hai — anjaan visitor ko nahi; team se rabta
                    reply_content = await self._escalate(
                        conversation.id, f"Order question from website visitor: '{text}'", lang
                    )
                else:
                    reply_content = await self.lookup_order_status(
                        store_id, text, lang, authenticated_email=authenticated_email
                    )

        elif intent == Intent.CART_ADD:
            if public:
                reply_content = await self._escalate(
                    conversation.id, f"Purchase request from website visitor: '{text}'", lang
                )
            else:
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

            # 2. Warna product (sirf asli match par), warna "samajh nahi aya"
            if not reply_content:
                reply_content = await self.answer_product_question(store_id, text, lang, strict=True)
            if not reply_content or "not found" in reply_content.lower() or "nahi mila" in reply_content.lower():
                reply_content = await self._not_understood_reply(store_id, lang)

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
            "silent": False,
            "conversation_status": conversation.status,
        }

    async def _escalate(self, conversation_id: int, reason: str, language: str) -> str:
        """Chat human ko do (handoff) aur customer ko batane wala message return karo."""
        await self.handoff_to_human(conversation_id, reason=reason)
        return (
            "Main ne aapki request human support team ko forward kar di hai. Ek agent jald aap se contact karega."
            if language in ("roman_urdu", "urdu")
            else "I have escalated your request to our human support team. A representative will get back to you shortly."
        )

    async def _handoff_waiting_reply(self, conversation: Conversation, language: str) -> dict:
        """Handoff chat mein customer ka naya message: pehli dafa "team jald jawab degi",
        uske baad (jab tak owner ka reply ya bot wapsi na ho) khamoshi."""
        waiting_texts = set(HANDOFF_WAITING_MESSAGES.values())
        last = (await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id, Message.role.in_(("agent_bot", "agent_human")))
            .order_by(Message.id.desc())
            .limit(1)
        )).scalar_one_or_none()

        base = {
            "conversation_id": conversation.id,
            "role": "agent_bot",
            "intent": "handoff_waiting",
            "language": language,
            "conversation_status": "handoff",
        }
        if last is not None and last.role == "agent_bot" and last.content in waiting_texts:
            # Pehle hi bata chuke hain — dobara na bolo
            return {**base, "message_id": 0, "content": "", "silent": True}

        text = HANDOFF_WAITING_MESSAGES.get(language, HANDOFF_WAITING_MESSAGES["en"])
        bot_msg = Message(conversation_id=conversation.id, role="agent_bot", content=text)
        self.db.add(bot_msg)
        await self.db.flush()
        return {**base, "message_id": bot_msg.id, "content": text, "silent": False}

    # ─── Policy questions that look like handoff keywords ───────

    # Sirf yeh keywords "info sawal" ho sakte hain; baaki (cancel, scam, legal, ...) hamesha handoff.
    _SOFT_HANDOFF_KEYWORDS = ("refund", "return policy")
    _ACTION_RE = re.compile(
        r"\b(i want|i need|i would like|i'd like|i demand|give me|process|issue|send me|mujhe|"
        r"refund me|refund my|my refund|money back|paisa wapas|paise wapas)\b|#\s?\d{3,}",
        re.IGNORECASE,
    )
    _INFO_RE = re.compile(
        r"\b(policy|policies|how|what|when|do you|does|can i|is there|are there|eligible|"
        r"window|days|kya|kaise|kitne|kab)\b|\?",
        re.IGNORECASE,
    )

    def _is_policy_question(self, text: str) -> bool:
        """True sirf tab jab matched handoff keywords soft hon aur message info maang raha ho,
        action nahi (e.g. "what is your refund policy?" haan; "I want a refund" nahi)."""
        lowered = text.lower()
        matched = [
            kw for kw in (*self.settings.HANDOFF_KEYWORDS, *self.settings.OUT_OF_SCOPE_KEYWORDS)
            if kw.lower() in lowered
        ]
        if not matched or any(kw.lower() not in self._SOFT_HANDOFF_KEYWORDS for kw in matched):
            return False
        if self._ACTION_RE.search(text):
            return False
        return bool(self._INFO_RE.search(text))

    async def _try_policy_answer(self, store_id: int, text: str, language: str) -> str:
        """Policy sawal ka jawab knowledge base se; "" agar sawal policy-type nahi ya KB mein jawab nahi."""
        if not self._is_policy_question(text):
            return ""
        hits = await self._knowledge_hits(store_id, text)
        return await self.answer_from_knowledge(text, language, hits) if hits else ""

    # ─── "Samajh nahi aya" reply ────────────────────────────────

    async def _knowledge_topics(self, store_id: int) -> list[str]:
        """Owner ki knowledge base ke document titles (hint ke liye). Fail hone par khali."""
        if not self.settings.KB_ENABLED:
            return []
        try:
            return await list_store_knowledge_topics(self.db, store_id, limit=4)
        except Exception as e:
            logger.warning(f"Knowledge topics lookup failed (store={store_id}): {e}")
            return []

    def _human_trigger_phrase(self) -> str:
        """Woh phrase jo handoff keywords mein hai, taake customer ka likha handoff trigger kare."""
        keywords = [kw.lower() for kw in self.settings.HANDOFF_KEYWORDS]
        for phrase in ("talk to human", "speak to representative"):
            if phrase in keywords:
                return phrase
        return ""

    async def _not_understood_reply(self, store_id: int, language: str) -> str:
        """Sawal samajh na aaye to: kya pooch sakte hain (hint) + human se baat ka option."""
        roman = language in ("roman_urdu", "urdu")
        topics = await self._knowledge_topics(store_id)
        phrase = self._human_trigger_phrase()

        if roman:
            text = "Aapka sawal samajh nahi aya. Kya aap product ka naam ya order number bata saktay hain?"
            if topics:
                text += f" Aap in ke baray me bhi pooch saktay hain: {', '.join(topics)}."
            else:
                text += " Aap products, stock ya apne order ke baray me pooch saktay hain."
            if phrase:
                text += f' Ya "{phrase}" likhein, main aap ko support team se mila doon ga.'
        else:
            text = "I'm not quite sure I understood. Could you please specify a product name or your order number?"
            if topics:
                text += f" You can also ask about: {', '.join(topics)}."
            else:
                text += " You can also ask about products, stock or your order status."
            if phrase:
                text += f' Or type "{phrase}" and I\'ll connect you with our support team.'
        return text

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
        strict: bool = False,
    ) -> str:
        """Answer product questions using live DB catalog (never guessed).

        knowledge_hits: owner ki knowledge base ke passages. Koi product match na ho
        to inhi se jawab diya jata hai (arbitrary pehla product dikhane se behtar);
        warna FAQ ke taur par LLM prompt mein jaate hain.

        strict: sirf asli (stopword ke ilawa) matching alfaz se product chuno. Koi product
        match na ho (ya catalog khali ho) to "" return hota hai — arbitrary pehla product
        ya "no products" message nahi — taake caller "samajh nahi aya" keh sake.
        """
        # Fetch active products for this store
        res = await self.db.execute(
            select(Product).where(Product.store_id == store_id)
        )
        products = res.scalars().all()

        if not products:
            if strict:
                return ""
            return (
                "Abhi store par koi products available nahi hain."
                if language in ("roman_urdu", "urdu")
                else "There are currently no products available in the store catalog."
            )

        # Score matching products by token overlap
        tokens = set(re.findall(r"\b\w{3,}\b", query.lower()))
        if strict:
            tokens -= STOPWORDS
            if not tokens:
                return ""
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

        if not top_matches and strict:
            return ""

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

    async def lookup_order_status(
        self,
        store_id: int,
        text: str,
        language: str = "en",
        authenticated_email: Optional[str] = None,
    ) -> str:
        """Lookup order status using local synced orders table.

        authenticated_email: email of the logged-in user, taken from the auth token by the caller
        (never from the chat text). Only that user's own orders are returned. A missing order and
        someone else's order get the SAME reply so the bot never confirms an order exists.
        """
        roman = language in ("roman_urdu", "urdu")
        not_found = (
            "Aapke account par yeh order nahi mila."
            if roman
            else "I couldn't find that order on your account."
        )

        if not authenticated_email:
            # Fail closed: without a verified identity we never read order data.
            return not_found

        # Emails are removed first so digits inside an address aren't mistaken for an order number.
        email_match = re.search(r"[\w\.-]+@[\w\.-]+", text)
        text_wo_email = re.sub(r"[\w\.-]+@[\w\.-]+", " ", text)
        order_match = re.search(r"#?\s?(\d{3,8})\b", text_wo_email)

        query = select(Order).where(
            Order.store_id == store_id,
            func.lower(Order.customer_email) == authenticated_email.strip().lower(),
        )

        if order_match:
            order_num = order_match.group(1)
            # Exact match only: "001" must not find order 1001.
            query = query.where(
                or_(
                    Order.order_number == order_num,
                    Order.order_number == f"#{order_num}",
                    Order.platform_order_id == order_num,
                )
            )
        elif email_match:
            # A typed email is only honoured if it is the logged-in user's own address.
            if email_match.group(0).lower() != authenticated_email.strip().lower():
                return not_found
            query = query.order_by(Order.ordered_at.desc())
        else:
            return (
                "Order status check karne ke liye apna Order Number (e.g. #1001) ya Email provide karein."
                if roman
                else "Please provide your Order Number (e.g. #1001) or email address to check the status."
            )

        res = await self.db.execute(query.limit(1))
        order = res.scalar_one_or_none()

        if not order:
            return not_found

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

        # Human jawab de raha hai → handoff mein hi rahe (bot beech mein na bole); bot ko wapas
        # dene ke liye inbox se status "open" karna hota hai.
        conv.status = "handoff"
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

    async def list_handoffs(
        self,
        store_id: Optional[int] = None,
        limit: int = 50,
        store_ids: Optional[list[int]] = None,
    ) -> list[HandoffLog]:
        """Handoff logs, newest first. store_id / store_ids se sirf un stores ki conversations
        (pehle store_id ignore hota tha aur sab stores ki handoffs wapas aati thin)."""
        ids = store_ids if store_ids is not None else ([store_id] if store_id is not None else None)
        query = select(HandoffLog)
        if ids is not None:
            query = query.join(Conversation, Conversation.id == HandoffLog.conversation_id).where(
                Conversation.store_id.in_(ids)
            )
        res = await self.db.execute(query.order_by(HandoffLog.created_at.desc(), HandoffLog.id.desc()).limit(limit))
        return list(res.scalars().all())
