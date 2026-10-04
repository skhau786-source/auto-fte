# ═══════════════════════════════════════════════════════════════
# agents / customer_support / api.py
#
# PURPOSE: REST API endpoints for Customer Support Agent.
# ═══════════════════════════════════════════════════════════════

import logging
from typing import Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.sdk.database import get_db
from src.sdk.models.base import Store
from src.sdk.models.support import Conversation

from src.domains.agents.customer_support.handler import CustomerSupportHandler
from src.domains.auth.service import get_current_user
from src.domains.ecommerce.routes import _get_store_or_404

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/support", tags=["Customer Support"])


async def _owned_conversation_or_404(db: AsyncSession, conversation_id: int, user) -> Conversation:
    """Conversation tabhi milti hai jab uska store isi user ka ho (warna 404, existence leak nahi)."""
    conv = (await db.execute(
        select(Conversation)
        .join(Store, Store.id == Conversation.store_id)
        .where(Conversation.id == conversation_id, Store.user_id == user.id)
    )).scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


# ─── Schemas ──────────────────────────────────────────────────

class ChatRequest(BaseModel):
    store_id: int
    message: str
    customer_email: str = "customer@example.com"
    conversation_id: Optional[int] = None
    language: str = ""


class HumanReplyRequest(BaseModel):
    text: str


# ─── Endpoints ────────────────────────────────────────────────

@router.post("/chat")
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Owner/dashboard chat endpoint (RAG, cart, order lookup, handoff) — sirf apne store par.

    Anjaan website visitors ke liye alag public endpoint hai:
    POST /api/v1/public/stores/{public_store_key}/chat
    """
    await _get_store_or_404(db, body.store_id, current_user.id)
    handler = CustomerSupportHandler(db)
    result = await handler.process_message(
        store_id=body.store_id,
        customer_email=body.customer_email,
        text=body.message,
        conversation_id=body.conversation_id,
        language=body.language,
    )
    await db.commit()
    return result


@router.post("/conversations/{conversation_id}/human-reply")
async def human_reply(
    conversation_id: int,
    body: HumanReplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Support dashboard endpoint: Human agent sends reply to conversation (store owner only)."""
    await _owned_conversation_or_404(db, conversation_id, current_user)
    handler = CustomerSupportHandler(db)
    try:
        msg = await handler.human_reply(conversation_id, body.text)
        await db.commit()
        return {
            "status": "posted",
            "message_id": msg.id,
            "conversation_id": conversation_id,
            "role": msg.role,
            "content": msg.content,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/conversations/{conversation_id}/close")
async def close_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Close an active support conversation (store owner only)."""
    await _owned_conversation_or_404(db, conversation_id, current_user)
    handler = CustomerSupportHandler(db)
    try:
        conv = await handler.close_conversation(conversation_id)
        await db.commit()
        return {"status": "closed", "conversation_id": conv.id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/conversations")
async def list_conversations(
    store_id: int = Query(...),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List customer support conversations (store owner only)."""
    await _get_store_or_404(db, store_id, current_user.id)
    handler = CustomerSupportHandler(db)
    convs = await handler.list_conversations(store_id, status)
    return [
        {
            "id": c.id,
            "store_id": c.store_id,
            "customer_email": c.customer_email,
            "status": c.status,
            "created_at": c.created_at,
            "closed_at": c.closed_at,
        }
        for c in convs
    ]


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get full conversation with message history (store owner only)."""
    await _owned_conversation_or_404(db, conversation_id, current_user)
    handler = CustomerSupportHandler(db)
    data = await handler.get_conversation(conversation_id)
    if not data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return data


@router.get("/handoffs")
async def list_handoffs(
    store_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List escalated conversations waiting for human attention.

    Sirf user ke apne stores ka data: store_id diya ho to us store ka (ownership check ke saath),
    warna user ke saare stores ka.
    """
    if store_id is not None:
        await _get_store_or_404(db, store_id, current_user.id)
        store_ids = [store_id]
    else:
        store_ids = list((await db.execute(
            select(Store.id).where(Store.user_id == current_user.id)
        )).scalars().all())
    handler = CustomerSupportHandler(db)
    handoffs = await handler.list_handoffs(limit=limit, store_ids=store_ids)
    return [
        {
            "id": h.id,
            "conversation_id": h.conversation_id,
            "reason": h.reason,
            "assigned_to": h.assigned_to,
            "created_at": h.created_at,
        }
        for h in handoffs
    ]
