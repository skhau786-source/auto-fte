"""Support chat logic: answers customers from the store's real data."""

import uuid
from decimal import Decimal

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product, ProductVariant, Store
from app.support_chat import nlu
from app.support_chat.models import SupportHandoff

T = {
    "en": {
        "greeting": "Hello! I can help with product prices, stock and order status. What would you like to know?",
        "thanks": "You're welcome! Anything else I can help with?",
        "unknown": "I'm not sure I understood. Ask me about a product's price or stock, an order status, or say \"talk to the owner\".",
        "product_found": "{title}: price {price}, {stock_text}.",
        "in_stock": "{n} in stock",
        "out_stock": "currently out of stock",
        "no_product": "I couldn't find a product matching \"{q}\". Try another name, or say \"talk to the owner\".",
        "ask_product": "Which product do you mean? Please type its name.",
        "ask_order": "Please send your order number (for example: order 1234).",
        "order_found": "Order #{number}: status is {status}, total {total} {currency}.",
        "order_missing": "I couldn't find order #{ref}. Please check the number, or say \"talk to the owner\" and they'll help.",
        "handoff": "I've passed your message to the store owner. They'll get back to you soon.",
        "handoff_contact": " If you'd like, leave your phone number or email in your next message.",
    },
    "ur": {
        "greeting": "Assalam o alaikum! Main products ki price, stock aur order status mein madad kar sakta hoon. Bataiye kya poochna hai?",
        "thanks": "Koi baat nahi! Aur kuch poochna hai?",
        "unknown": "Mujhe samajh nahi aaya. Aap kisi product ki price/stock, order status poochein, ya likhein \"owner se baat karni hai\".",
        "product_found": "{title}: qeemat {price}, {stock_text}.",
        "in_stock": "{n} stock mein maujood hain",
        "out_stock": "abhi stock khatam hai",
        "no_product": "\"{q}\" naam ka koi product nahi mila. Doosra naam try karein, ya likhein \"owner se baat karni hai\".",
        "ask_product": "Kaun sa product? Meherbani karke uska naam likhein.",
        "ask_order": "Meherbani karke apna order number bhejein (masalan: order 1234).",
        "order_found": "Order #{number}: status {status} hai, total {total} {currency}.",
        "order_missing": "Order #{ref} nahi mila. Number dobara check karein, ya likhein \"owner se baat karni hai\".",
        "handoff": "Maine aapka paigham store owner ko bhej diya hai. Woh jald aap se rabta karenge.",
        "handoff_contact": " Agar chahein to agle message mein apna phone number ya email likh dein.",
    },
}


def _money(v) -> str:
    return f"{Decimal(v):,.2f}"


async def find_product(db: AsyncSession, store_id: uuid.UUID, terms: list[str]):
    """Best matching active product by title / type / SKU, or None."""
    if not terms:
        return None
    conds = []
    for t in terms:
        like = f"%{t}%"
        conds.append(Product.title.ilike(like))
        conds.append(Product.product_type.ilike(like))
        conds.append(Product.id.in_(select(ProductVariant.product_id).where(ProductVariant.sku.ilike(like))))
    rows = (
        await db.execute(
            select(Product)
            .where(Product.store_id == store_id, Product.status == "active", or_(*conds))
            .limit(25)
        )
    ).scalars().all()
    if not rows:
        return None
    return max(rows, key=lambda p: sum(1 for t in terms if t in p.title.lower()))


async def _variants(db: AsyncSession, product_id: uuid.UUID) -> list[ProductVariant]:
    return list(
        (await db.execute(select(ProductVariant).where(ProductVariant.product_id == product_id))).scalars()
    )


async def find_order(db: AsyncSession, store: Store, ref: str):
    """Look the order up in the owner's WooCommerce orders (the only order table that exists)."""
    from app.woocommerce.models import WooCommerceOrder, WooCommerceStore

    q = (
        select(WooCommerceOrder)
        .join(WooCommerceStore, WooCommerceStore.id == WooCommerceOrder.store_id)
        .where(
            WooCommerceStore.owner_id == store.owner_id,
            or_(WooCommerceOrder.number == ref, WooCommerceOrder.wc_order_id == int(ref)),
        )
        .limit(1)
    )
    return (await db.execute(q)).scalar_one_or_none()


async def create_handoff(db, store_id, session_id, message, lang, name, contact, transcript) -> SupportHandoff:
    h = SupportHandoff(
        store_id=store_id,
        session_id=session_id[:100],
        customer_name=name[:150] if name else None,
        customer_contact=contact[:150] if contact else None,
        message=message[:1000],
        language=lang,
        transcript=(transcript or [])[-20:],
    )
    db.add(h)
    await db.commit()
    await db.refresh(h)
    return h


async def answer(db: AsyncSession, store: Store, session_id: str, message: str,
                 name: str | None, contact: str | None, history: list[dict]) -> dict:
    lang = nlu.detect_language(message)
    # Short follow-ups ("iphone?") keep the language of the recent conversation.
    if lang == "en" and len(nlu.tokenize(message)) <= 3 and any(m.get("lang") == "ur" for m in history[-4:]):
        lang = "ur"
    t = T[lang]
    intent = nlu.detect_intent(message)
    out = {"intent": intent, "language": lang, "handoff_id": None, "product": None}

    if intent == "greeting":
        out["reply"] = t["greeting"]
    elif intent == "thanks":
        out["reply"] = t["thanks"]
    elif intent == "handoff":
        h = await create_handoff(db, store.id, session_id, message, lang, name, contact, history)
        out["handoff_id"] = str(h.id)
        out["reply"] = t["handoff"] + ("" if contact else t["handoff_contact"])
    elif intent == "order":
        ref = nlu.extract_order_ref(message)
        if not ref:
            out["reply"] = t["ask_order"]
        else:
            order = await find_order(db, store, ref)
            if order:
                status = getattr(order.status, "value", order.status)
                out["reply"] = t["order_found"].format(
                    number=order.number, status=str(status).replace("-", " "),
                    total=_money(order.total), currency=order.currency or "")
            else:
                out["reply"] = t["order_missing"].format(ref=ref)
    elif intent in ("price", "stock", "product"):
        terms = nlu.product_terms(message)
        if not terms:
            out["reply"] = t["ask_product"]
        else:
            p = await find_product(db, store.id, terms)
            if not p:
                out["reply"] = t["no_product"].format(q=" ".join(terms))
            else:
                vs = await _variants(db, p.id)
                total = sum(max(v.inventory_quantity, 0) for v in vs)
                prices = [v.price for v in vs] or [Decimal("0")]
                lo, hi = min(prices), max(prices)
                price = _money(lo) if lo == hi else f"{_money(lo)} - {_money(hi)}"
                stock_text = t["in_stock"].format(n=total) if total > 0 else t["out_stock"]
                out["reply"] = t["product_found"].format(title=p.title, price=price, stock_text=stock_text)
                out["product"] = {"id": str(p.id), "title": p.title, "price": price, "stock": total}
    else:
        out["reply"] = t["unknown"]
    return out
