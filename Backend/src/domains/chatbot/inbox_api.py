# ═══════════════════════════════════════════════════════════════
# domains / chatbot / inbox_api.py
#
# PURPOSE: Owner support inbox endpoints (store ownership enforced).
#
#   GET  /api/v1/stores/{store_id}/inbox?status=&page=&page_size=
#   GET  /api/v1/stores/{store_id}/inbox/{conversation_id}
#   POST /api/v1/stores/{store_id}/inbox/{conversation_id}/reply
#   POST /api/v1/stores/{store_id}/inbox/{conversation_id}/status
# ═══════════════════════════════════════════════════════════════

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.sdk.database import get_db
from src.sdk.exceptions import AgentError
from src.domains.auth.models import User
from src.domains.auth.service import get_current_user
from src.domains.ecommerce.routes import _get_store_or_404
from src.domains.chatbot.inbox_service import InboxService, MAX_REPLY_CHARS

router = APIRouter(prefix="/api/v1", tags=["Support Inbox"])


class ReplyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_REPLY_CHARS)


class StatusRequest(BaseModel):
    status: str = Field(description="open | handoff | closed")


class ConversationItem(BaseModel):
    id: int
    customer_email: str
    status: str
    created_at: datetime
    last_activity: datetime
    last_message: str
    last_role: Optional[str]
    awaiting_reply: bool
    message_count: int
    handoff_reason: Optional[str]


class InboxResponse(BaseModel):
    items: list[ConversationItem]
    total: int
    page: int
    page_size: int
    counts: dict[str, int]


def _http_error(exc: AgentError) -> HTTPException:
    return HTTPException(status_code=exc.code if exc.code in (400, 404, 409) else 400, detail=exc.message)


async def _service(store_id: int, user: User, db: AsyncSession) -> InboxService:
    await _get_store_or_404(db, store_id, user.id)
    return InboxService(db, store_id)


@router.get("/stores/{store_id}/inbox", response_model=InboxResponse)
async def list_inbox(
    store_id: int,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = await _service(store_id, user, db)
    try:
        items, total = await service.list_conversations(status, page, page_size)
    except AgentError as exc:
        raise _http_error(exc)
    return InboxResponse(
        items=items, total=total, page=page, page_size=page_size, counts=await service.counts()
    )


@router.get("/stores/{store_id}/inbox/{conversation_id}")
async def get_thread(
    store_id: int,
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = await _service(store_id, user, db)
    try:
        return await service.get_thread(conversation_id)
    except AgentError as exc:
        raise _http_error(exc)


@router.post("/stores/{store_id}/inbox/{conversation_id}/reply", status_code=201)
async def reply(
    store_id: int,
    conversation_id: int,
    payload: ReplyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = await _service(store_id, user, db)
    try:
        msg = await service.reply(conversation_id, payload.text)
    except AgentError as exc:
        await db.rollback()
        raise _http_error(exc)
    return {"id": msg.id, "role": msg.role, "content": msg.content, "created_at": msg.created_at}


@router.post("/stores/{store_id}/inbox/{conversation_id}/status")
async def set_status(
    store_id: int,
    conversation_id: int,
    payload: StatusRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = await _service(store_id, user, db)
    try:
        conv = await service.set_status(conversation_id, payload.status)
    except AgentError as exc:
        await db.rollback()
        raise _http_error(exc)
    return {"id": conv.id, "status": conv.status, "closed_at": conv.closed_at}
