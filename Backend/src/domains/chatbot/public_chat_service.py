# ═══════════════════════════════════════════════════════════════
# domains / chatbot / public_chat_service.py
#
# PURPOSE: Public website chat ke building blocks — store public key
#          aur anonymous visitor sessions.
#
# USED BY: domains/chatbot/public_chat_api.py
#
# SECURITY:
#   - Public key secret nahi, sirf pehchan hai (page source mein hoti hai).
#   - Visitor session token random hai; DB mein sirf SHA-256 hash.
#   - Session store se bandha hai aur ek hi conversation se; visitor
#     kisi aur ki chat address hi nahi kar sakta.
# ═══════════════════════════════════════════════════════════════

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.sdk.models.base import Store
from src.sdk.models.public_chat import StorePublicKey, VisitorSession

KEY_PREFIX = "pk_"
SESSION_PREFIX = "vs_"


def generate_public_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(18)


def generate_session_token() -> str:
    return SESSION_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ─── Public key (owner side) ──────────────────────────────────

async def get_or_create_public_key(db: AsyncSession, store_id: int) -> StorePublicKey:
    row = (await db.execute(
        select(StorePublicKey).where(StorePublicKey.store_id == store_id)
    )).scalar_one_or_none()
    if row is None:
        row = StorePublicKey(store_id=store_id, public_key=generate_public_key(), enabled=True)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def rotate_public_key(db: AsyncSession, store_id: int) -> StorePublicKey:
    """Nayi key; purani foran bekaar (uske widgets 404 denge)."""
    row = await get_or_create_public_key(db, store_id)
    row.public_key = generate_public_key()
    row.rotated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


async def set_public_chat_enabled(db: AsyncSession, store_id: int, enabled: bool) -> StorePublicKey:
    row = await get_or_create_public_key(db, store_id)
    row.enabled = enabled
    await db.commit()
    await db.refresh(row)
    return row


# ─── Public side ──────────────────────────────────────────────

async def resolve_public_store(db: AsyncSession, public_key: str) -> Optional[Store]:
    """Key se store — sirf agar key enabled ho aur store active."""
    if not public_key or not public_key.startswith(KEY_PREFIX) or len(public_key) > 64:
        return None
    return (await db.execute(
        select(Store)
        .join(StorePublicKey, StorePublicKey.store_id == Store.id)
        .where(
            StorePublicKey.public_key == public_key,
            StorePublicKey.enabled == True,  # noqa: E712
            Store.is_active == True,  # noqa: E712
        )
    )).scalar_one_or_none()


async def create_visitor_session(db: AsyncSession, store_id: int) -> tuple[VisitorSession, str]:
    token = generate_session_token()
    session = VisitorSession(store_id=store_id, token_hash=hash_token(token))
    db.add(session)
    await db.flush()  # id chahiye (visitor label ke liye)
    return session, token


async def find_visitor_session(
    db: AsyncSession,
    store_id: int,
    token: Optional[str],
    ttl_days: int,
    lock: bool = False,
) -> Optional[VisitorSession]:
    """Session sirf isi store ka, aur ttl ke andar. Warna None (forged/expired/doosre store ka)."""
    if not token or not token.startswith(SESSION_PREFIX) or len(token) > 128:
        return None
    stmt = select(VisitorSession).where(
        VisitorSession.token_hash == hash_token(token),
        VisitorSession.store_id == store_id,
        VisitorSession.last_seen_at > datetime.now(timezone.utc) - timedelta(days=ttl_days),
    )
    if lock:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()
