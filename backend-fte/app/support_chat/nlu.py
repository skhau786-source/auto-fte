"""Rule-based understanding for the support chat (English + Roman Urdu).

No LLM key is required. Pure functions only, so it is easy to unit-test.
"""

import re

GREETING = {"hi", "hello", "hey", "salam", "salaam", "assalam", "assalamualaikum", "aoa", "slam", "asalam", "alaikum", "alaikom", "walaikum", "salamualaikum", "o", "wa", "good", "morning", "evening"}
THANKS = {"thanks", "thank", "thx", "shukriya", "shukria", "jazakallah", "jazak", "meherbani", "mehrbani"}
PRICE = {"price", "cost", "rate", "rates", "pricing", "kitne", "kitna", "kitni", "qeemat", "keemat",
         "qimat", "kimat", "daam", "dam", "paisay", "paise", "rupay"}
STOCK = {"stock", "available", "availability", "instock", "maujood", "mojood", "mojud", "bacha", "bache",
         "bachay", "baqi", "baaki", "milega", "milegi", "avail"}
ORDER = {"order", "tracking", "track", "parcel", "delivery", "deliver", "shipment", "shipped", "dispatch",
         "status", "kahan", "kahaan", "pohanch", "pahunch", "aya", "aaya", "ayega", "aayega", "ordr"}
HANDOFF = {"human", "agent", "owner", "malik", "representative", "person", "insaan", "complaint",
           "shikayat", "shikayet", "manager", "helpline"}

URDU_MARKERS = {"kya", "hai", "hain", "ka", "ki", "ke", "mein", "main", "me", "kitna", "kitne", "kitni",
                "kahan", "kab", "mujhe", "mera", "meri", "aap", "ap", "chahiye", "karni", "karna", "karo",
                "kijiye", "bhai", "shukriya", "shukria", "salam", "assalam", "aoa", "qeemat", "keemat",
                "daam", "maujood", "mojood", "milega", "milegi", "baqi", "malik", "shikayat", "nahi",
                "nahin", "abhi", "wala", "wali", "se", "ko", "aya", "ayega", "pohanch", "bacha", "bache",
                "baat", "batao", "bataiye", "yeh", "woh", "kab"}

STOPWORDS = (PRICE | STOCK | ORDER | HANDOFF | GREETING | THANKS | URDU_MARKERS) | {
    "the", "a", "an", "is", "are", "of", "for", "to", "do", "you", "have", "what", "how", "much", "many",
    "this", "that", "in", "on", "my", "i", "it", "please", "pls", "plz", "can", "tell", "about",
    "any", "there", "left", "with", "and", "or", "im", "want", "need", "know", "show", "get", "talk",
    "ye", "wo", "bata", "dikhao", "lena", "available", "call", "support",
}

ORDER_REF = re.compile(r"(?:#|order\s*(?:no|number|id)?\s*[:#]?\s*|wc-?)(\d{2,})", re.I)
BARE_NUMBER = re.compile(r"\b(\d{3,})\b")


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def detect_language(text: str) -> str:
    """'ur' for Roman Urdu, 'en' otherwise."""
    toks = tokenize(text)
    hits = sum(1 for t in toks if t in URDU_MARKERS)
    return "ur" if hits >= 1 and hits >= max(1, len(toks) // 5) else "en"


def extract_order_ref(text: str) -> str | None:
    m = ORDER_REF.search(text)
    if m:
        return m.group(1)
    if set(tokenize(text)) & ORDER:
        m = BARE_NUMBER.search(text)
        if m:
            return m.group(1)
    return None


def product_terms(text: str) -> list[str]:
    """Words that probably name a product (everything that is not a function word)."""
    return [t for t in tokenize(text) if t not in STOPWORDS and len(t) >= 3 and not t.isdigit()]


def detect_intent(text: str) -> str:
    """One of: handoff, order, price, stock, greeting, thanks, product, unknown."""
    toks = set(tokenize(text))
    phrase = " ".join(tokenize(text))
    if (toks & HANDOFF or "baat karni" in phrase or "baat karna" in phrase or "baat kar" in phrase
            or "talk to" in phrase or "speak to" in phrase or "call me" in phrase):
        return "handoff"
    if extract_order_ref(text) or ({"order", "tracking", "track", "parcel", "delivery", "ordr"} & toks):
        return "order"
    if toks & (PRICE - {"kitne", "kitna", "kitni"}):
        return "price"
    if toks & STOCK or "in stock" in phrase or "stock mein" in phrase:
        return "stock"
    if toks & PRICE or "how much" in phrase:
        return "price"
    if toks and toks <= GREETING:
        return "greeting"
    if product_terms(text):
        return "product"
    if toks & THANKS:
        return "thanks"
    if toks & GREETING:
        return "greeting"
    return "unknown"
