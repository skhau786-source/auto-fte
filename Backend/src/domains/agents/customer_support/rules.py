# ═══════════════════════════════════════════════════════════════
# agents / customer_support / rules.py
#
# PURPOSE: Intent classification, language detection, and answer
#          formatting for Customer Support Agent.
# ═══════════════════════════════════════════════════════════════

import re
from enum import Enum
from typing import Optional


class Intent(str, Enum):
    PRODUCT_QUESTION = "product_question"
    ORDER_STATUS = "order_status"
    CART_ADD = "cart_add"
    CART_REMOVE = "cart_remove"
    CART_UPDATE = "cart_update"
    OUT_OF_SCOPE = "out_of_scope"
    GREETING = "greeting"
    FALLBACK = "fallback"


def detect_language(text: str) -> str:
    """Detect if text is Urdu script, Roman Urdu, or English."""
    # Check for Arabic/Urdu script Unicode range (0600-06FF)
    if re.search(r"[؀-ۿ]", text):
        return "urdu"

    # Common Roman Urdu markers
    roman_urdu_markers = [
        "kya", "kiya", "hai", "hain", "kahan", "kitna", "kitne", "kitni",
        "chahiye", "bhai", "batao", "mujhe", "mera", "meri", "acha",
        "kab", "milay", "ga", "gi", "kaise", "hoga", "ap", "aap", "shukriya"
    ]
    words = re.findall(r"\b\w+\b", text.lower())
    matches = sum(1 for w in words if w in roman_urdu_markers)
    if matches >= 2 or (len(words) <= 4 and matches >= 1):
        return "roman_urdu"

    return "en"


def classify_intent(
    text: str,
    handoff_keywords: Optional[list[str]] = None,
    out_of_scope_keywords: Optional[list[str]] = None,
) -> Intent:
    """Classify customer message into a support intent."""
    lowered = text.lower()
    handoff_kw = handoff_keywords or [
        "refund", "cancel my order", "cancel order", "return policy",
        "scam", "fraud", "sue", "legal", "talk to human", "speak to representative"
    ]
    out_of_scope_kw = out_of_scope_keywords or ["refund", "cancel", "chargeback", "lawyer"]

    # 1. Check out of scope / human handoff keywords first
    for kw in handoff_kw:
        if kw.lower() in lowered:
            return Intent.OUT_OF_SCOPE

    # 2. Check Cart Operations (add/buy first so 'order this' isn't confused with order status)
    if any(re.search(p, lowered) for p in [r"\badd\b.*\bcart\b", r"\bbuy\b", r"cart me (daal|add)", r"order this"]):
        return Intent.CART_ADD
    if any(re.search(p, lowered) for p in [r"\bremove\b.*\bcart\b", r"cart se nikal"]):
        return Intent.CART_REMOVE
    if any(re.search(p, lowered) for p in [r"\bview cart\b", r"\bmy cart\b", r"\bcart\b"]):
        return Intent.CART_UPDATE

    # 3. Check Order Status
    order_patterns = [
        r"\border status\b", r"\btracking\b", r"\btrack\b", r"\bshipped\b",
        r"\bdelivery\b", r"where is my order", r"where is my", r"kahan hai", r"\border #?\d+"
    ]
    if any(re.search(p, lowered) for p in order_patterns):
        return Intent.ORDER_STATUS

    # 4. Check Greeting
    greetings = ["hi", "hello", "hey", "salam", "assalam", "good morning", "good evening"]
    words = set(re.findall(r"\b\w+\b", lowered))
    if any(g in words for g in greetings) and len(words) <= 3:
        return Intent.GREETING

    # 5. Product Question triggers
    product_patterns = [
        r"\bprice\b", r"\bcost\b", r"\bstock\b", r"\bavailable\b",
        r"\bsize\b", r"\bcolor\b", r"\bmaterial\b", r"kitna", r"kitne",
        r"hai kya", r"\bhow much\b", "details", "info",
        r"qeemat", r"keemat", r"kimat", r"qimat", r"\bdaam\b", r"\brate\b"
    ]
    if any(re.search(p, lowered) for p in product_patterns):
        return Intent.PRODUCT_QUESTION

    return Intent.FALLBACK


def format_product_answer(
    title: str,
    price: float,
    inventory_quantity: int,
    language: str = "en",
    description: str = "",
) -> str:
    """Format accurate product answer with live price & stock (never guessed)."""
    in_stock = inventory_quantity > 0
    stock_text_en = f"In stock ({inventory_quantity} available)" if in_stock else "Currently out of stock"
    stock_text_ru = f"Stock available hai ({inventory_quantity} units)" if in_stock else "Abhi out of stock hai"

    if language in ("roman_urdu", "urdu"):
        reply = f"**{title}** ki price **${price:.2f}** hai. {stock_text_ru}."
        if description:
            # take first sentence of description
            clean_desc = description.replace("\n", " ").strip()
            if len(clean_desc) > 120:
                clean_desc = clean_desc[:120] + "..."
            reply += f" ({clean_desc})"
        return reply

    reply = f"**{title}** is available for **${price:.2f}**. Status: {stock_text_en}."
    if description:
        clean_desc = description.replace("\n", " ").strip()
        if len(clean_desc) > 120:
            clean_desc = clean_desc[:120] + "..."
        reply += f" Description: {clean_desc}"
    return reply


def build_rag_context(products_and_variants: list) -> str:
    """Build a clean text context block for LLM prompt."""
    lines = []
    for item in products_and_variants:
        product = item.get("product")
        variants = item.get("variants", [])
        var_strs = [f"SKU: {v.sku}, Price: ${float(v.price):.2f}, Stock: {v.inventory_quantity}" for v in variants]
        lines.append(
            f"Product: {product.title}\n"
            f"Description: {product.description or 'N/A'}\n"
            f"Type: {product.product_type or 'N/A'}\n"
            f"Variants: {'; '.join(var_strs)}\n"
        )
    return "\n---\n".join(lines)
