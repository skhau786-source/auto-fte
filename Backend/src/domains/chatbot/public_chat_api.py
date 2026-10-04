# ═══════════════════════════════════════════════════════════════
# domains / chatbot / public_chat_api.py
#
# PURPOSE: Store website par anjaan visitors (bina login) ki chat.
#
# PUBLIC (koi login nahi; store public key + visitor session token):
#   POST /api/v1/public/stores/{public_key}/chat
#   GET  /api/v1/public/stores/{public_key}/chat/messages?after_id=
#
# OWNER (login + store ownership):
#   GET  /api/v1/stores/{store_id}/public-chat           key (pehli baar banti hai)
#   POST /api/v1/stores/{store_id}/public-chat/rotate    nayi key, purani bekaar
#   PUT  /api/v1/stores/{store_id}/public-chat           {enabled: bool}
#
# Visitor sirf: sawal poochna, product price/stock/policy jawab lena, apni chat poll karna.
# Order lookup / cart / koi edit nahi, aur kisi doosre store ya visitor ka data nahi.
# ═══════════════════════════════════════════════════════════════

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.sdk.config import get_settings
from src.sdk.database import get_db
from src.sdk.models.support import Conversation, Message
from src.domains.auth.models import User
from src.domains.auth.service import get_current_user
from src.domains.agents.customer_support.handler import CustomerSupportHandler
from src.domains.ecommerce.routes import _get_store_or_404
from src.domains.security.sliding_window import SlidingWindowLimiter, client_ip
from src.domains.chatbot.public_chat_service import (
    create_visitor_session,
    find_visitor_session,
    get_or_create_public_key,
    resolve_public_store,
    rotate_public_key,
    set_public_chat_enabled,
)

logger = logging.getLogger(__name__)

public_router = APIRouter(prefix="/api/v1/public/stores/{public_key}", tags=["Public Chat"])
owner_router = APIRouter(prefix="/api/v1/stores/{store_id}/public-chat", tags=["Public Chat (owner)"])

limiter = SlidingWindowLimiter()  # tests reset() karte hain

ALLOWED_LANGUAGES = {"en", "roman_urdu", "urdu"}
TOUCH_INTERVAL = timedelta(minutes=5)


# ─── Schemas ──────────────────────────────────────────────────

class PublicChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    preferred_language: Optional[str] = None


class PublicChatResponse(BaseModel):
    answer: str
    silent: bool = False
    conversation_status: str = "open"
    language: str = "en"
    session_token: Optional[str] = Field(
        default=None, description="Sirf pehle jawab mein: widget isay save kare aur X-Visitor-Session mein bheje"
    )


class PublicMessage(BaseModel):
    id: int
    content: str
    created_at: datetime


class PublicMessagesResponse(BaseModel):
    status: str
    messages: list[PublicMessage]


class PublicChatInfo(BaseModel):
    public_key: str
    enabled: bool


class EnabledRequest(BaseModel):
    enabled: bool


# ─── Helpers ──────────────────────────────────────────────────

def _rate_limit(key: str, limit: int, window_seconds: int) -> None:
    allowed, retry_after = limiter.hit(key, limit, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down and try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )


def _not_found(what: str = "Not found") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=what)


def _ensure_enabled() -> None:
    if not get_settings().PUBLIC_CHAT_ENABLED:
        raise _not_found()


# ─── Public: chat ─────────────────────────────────────────────

@public_router.post("/chat", response_model=PublicChatResponse)
async def public_chat(
    public_key: str,
    body: PublicChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_visitor_session: Optional[str] = Header(default=None),
):
    settings = get_settings()
    _ensure_enabled()
    ip = client_ip(request, settings.TRUST_PROXY_HEADERS)

    # Pehle sasti jaanch: IP limit (key guess karne ki koshishon par bhi lagti hai)
    _rate_limit(f"chat:ip:{ip}", settings.PUBLIC_CHAT_CHAT_PER_IP_PER_MINUTE, 60)

    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    if len(query) > settings.PUBLIC_CHAT_MAX_QUERY_CHARS:
        raise HTTPException(
            status_code=422, detail=f"Message is too long (max {settings.PUBLIC_CHAT_MAX_QUERY_CHARS} characters)"
        )

    store = await resolve_public_store(db, public_key)
    if store is None:
        raise _not_found("Store not found")

    session = await find_visitor_session(
        db, store.id, x_visitor_session, settings.PUBLIC_CHAT_SESSION_TTL_DAYS, lock=True
    )
    new_token: Optional[str] = None
    if session is None:
        # Token na ho / ghalat ho / expire ho → nayi anonymous chat (purani chat tak koi rasai nahi)
        _rate_limit(f"newsession:ip:{ip}", settings.PUBLIC_CHAT_NEW_SESSIONS_PER_IP_PER_HOUR, 3600)
        session, new_token = await create_visitor_session(db, store.id)

    _rate_limit(f"chat:session:{session.id}", settings.PUBLIC_CHAT_CHAT_PER_SESSION_PER_MINUTE, 60)

    language = body.preferred_language if body.preferred_language in ALLOWED_LANGUAGES else ""
    result = await CustomerSupportHandler(db).process_message(
        store_id=store.id,
        customer_email=f"visitor-{session.id}@anonymous.invalid",
        text=query,
        conversation_id=session.conversation_id,
        language=language,
        public=True,
    )

    session.conversation_id = result["conversation_id"]
    session.last_seen_at = datetime.now(timezone.utc)
    await db.commit()

    return PublicChatResponse(
        answer=result.get("content") or "",
        silent=bool(result.get("silent", False)),
        conversation_status=result.get("conversation_status", "open"),
        language=result.get("language", language or "en"),
        session_token=new_token,
    )


# ─── Public: poll support replies ─────────────────────────────

@public_router.get("/chat/messages", response_model=PublicMessagesResponse)
async def public_chat_messages(
    public_key: str,
    request: Request,
    after_id: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    x_visitor_session: Optional[str] = Header(default=None),
):
    """Visitor ki apni chat mein support team ke naye replies. Conversation id visitor deta hi nahi —
    session token se hi apni chat milti hai, isliye doosre ki chat address karna mumkin nahi."""
    settings = get_settings()
    _ensure_enabled()
    ip = client_ip(request, settings.TRUST_PROXY_HEADERS)
    _rate_limit(f"poll:ip:{ip}", settings.PUBLIC_CHAT_POLL_PER_IP_PER_MINUTE, 60)

    store = await resolve_public_store(db, public_key)
    if store is None:
        raise _not_found("Store not found")

    session = await find_visitor_session(db, store.id, x_visitor_session, settings.PUBLIC_CHAT_SESSION_TTL_DAYS)
    if session is None:
        raise _not_found("Session not found")

    _rate_limit(f"poll:session:{session.id}", settings.PUBLIC_CHAT_POLL_PER_SESSION_PER_MINUTE, 60)

    if session.conversation_id is None:
        return PublicMessagesResponse(status="open", messages=[])

    conv = (await db.execute(
        select(Conversation).where(
            Conversation.id == session.conversation_id, Conversation.store_id == store.id
        )
    )).scalar_one_or_none()
    if conv is None:
        raise _not_found("Session not found")

    rows = (await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id, Message.role == "agent_human", Message.id > after_id)
        .order_by(Message.id)
        .limit(50)
    )).scalars().all()

    # last_seen kabhi kabhi hi likho (har poll par DB write nahi)
    if datetime.now(timezone.utc) - session.last_seen_at > TOUCH_INTERVAL:
        session.last_seen_at = datetime.now(timezone.utc)
        await db.commit()

    return PublicMessagesResponse(
        status=conv.status,
        messages=[PublicMessage(id=m.id, content=m.content, created_at=m.created_at) for m in rows],
    )


# ─── Owner: key management ────────────────────────────────────

@owner_router.get("", response_model=PublicChatInfo)
async def get_public_chat_info(
    store_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_store_or_404(db, store_id, user.id)
    row = await get_or_create_public_key(db, store_id)
    return PublicChatInfo(public_key=row.public_key, enabled=row.enabled)


@owner_router.post("/rotate", response_model=PublicChatInfo)
async def rotate_key(
    store_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_store_or_404(db, store_id, user.id)
    row = await rotate_public_key(db, store_id)
    return PublicChatInfo(public_key=row.public_key, enabled=row.enabled)


@owner_router.put("", response_model=PublicChatInfo)
async def set_enabled(
    store_id: int,
    payload: EnabledRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_store_or_404(db, store_id, user.id)
    row = await set_public_chat_enabled(db, store_id, payload.enabled)
    return PublicChatInfo(public_key=row.public_key, enabled=row.enabled)
