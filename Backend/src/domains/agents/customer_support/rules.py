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


# ─── Cart quantity parsing ─────────────────────────────────────

# Unambiguous number words (English + Roman Urdu). "do" (= 2 in Urdu) is handled separately
# because it also means "give" / "do" ("cart me daal do", "do you have ...").
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "ek": 1, "teen": 3, "char": 4, "chaar": 4, "panch": 5, "paanch": 5, "chhe": 6, "che": 6, "chay": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10,
}
_QTY_BLOCKING_PREV = {"size", "no", "number", "model", "sku", "id", "item"}
_UNIT_AFTER = {"x", "pcs", "pc", "pieces", "piece", "items", "units", "unit"}
MAX_CART_QUANTITY = 99


def parse_quantity(text: str, product_title_tokens: Optional[set[str]] = None) -> tuple[Optional[int], bool]:
    """Quantity the customer asked for: (value, explicit).

    Reads digits ("2", "2x", "x2") and number words in English and Roman Urdu ("two", "teen").
    Numbers that belong to the product's own name ("Toaster 9000") and numbers after "size"/"model"
    are not quantities. No number at all -> (1, False). Returns (0, True) etc. unchanged so the
    caller can reject nonsense like 0.
    """
    title_tokens = {t.lower() for t in (product_title_tokens or set())}
    tokens = re.findall(r"[a-zA-Z]+|\d+", text.lower())
    for i, tok in enumerate(tokens):
        prev = tokens[i - 1] if i else ""
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if tok.isdigit():
            if tok in title_tokens or prev in _QTY_BLOCKING_PREV or len(tok) > 4:
                continue
            return int(tok), True
        if tok in NUMBER_WORDS and tok not in title_tokens:
            return NUMBER_WORDS[tok], True
        if tok == "do" and nxt and nxt in title_tokens and prev not in {"daal", "dal", "daalo", "kar", "karo", "de", "dedo"}:
            return 2, True  # "do Denim Jacket chahiye"
    return 1, False
