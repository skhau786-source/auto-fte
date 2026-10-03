"""Support chat routes.

Public (customers, no login):  POST /support-chat/message
                               POST /support-chat/handoff-contact
Owner (login required):        GET  /support-chat/my-stores
                               GET  /support-chat/handoffs
                               POST /support-chat/handoffs/{id}/resolve
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent, Store
from app.support_chat import service
from app.support_chat.models import SupportHandoff

router = APIRouter(prefix="/support-chat", tags=["Support Chat"])


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(customer|bot)$")
    text: str = Field(max_length=1000)
    lang: str | None = None


class ChatMessageIn(BaseModel):
    store_id: uuid.UUID
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)
    customer_name: str | None = Field(default=None, max_length=150)
    customer_contact: str | None = Field(default=None, max_length=150)
    history: list[ChatTurn] = Field(default_factory=list, max_length=30)


class ChatMessageOut(BaseModel):
    reply: str
    intent: str
    language: str
    handoff_id: str | None = None
    product: dict | None = None
    source: str = "rules"  # "rules" or "llm"


class HandoffOut(BaseModel):
    id: uuid.UUID
    store_id: uuid.UUID
    session_id: str
    customer_name: str | None
    customer_contact: str | None
    message: str
    language: str
    transcript: list | None
    status: str
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


class HandoffContactIn(BaseModel):
    handoff_id: uuid.UUID
    session_id: str = Field(min_length=1, max_length=100)
    contact: str = Field(min_length=3, max_length=150)


class StoreOut(BaseModel):
    id: uuid.UUID
    shopify_domain: str


@router.post("/message", response_model=ChatMessageOut)
async def chat_message(body: ChatMessageIn, db: AsyncSession = Depends(get_db)):
    """Answer a customer message. Public: the store is identified by store_id."""
    store = (
        await db.execute(select(Store).where(Store.id == body.store_id, Store.is_active == True))  # noqa: E712
    ).scalar_one_or_none()
    if not store:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Store not found")
    history = [t.model_dump() for t in body.history]
    return await service.answer(
        db, store, body.session_id, body.message, body.customer_name, body.customer_contact, history
    )


@router.post("/handoff-contact", status_code=status.HTTP_204_NO_CONTENT)
async def handoff_contact(body: HandoffContactIn, db: AsyncSession = Depends(get_db)):
    """Customer leaves a phone/email for an open handoff (must come from the same chat session)."""
    h = (
        await db.execute(
            select(SupportHandoff).where(
                SupportHandoff.id == body.handoff_id,
                SupportHandoff.session_id == body.session_id,
                SupportHandoff.status == "open",
            )
        )
    ).scalar_one_or_none()
    if not h:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Handoff not found")
    h.customer_contact = body.contact
    await db.commit()


@router.get("/my-stores", response_model=list[StoreOut])
async def my_stores(user: RegisteredStudent = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Store ids the owner can embed the chat widget for (/chat?store=<id>)."""
    rows = (await db.execute(select(Store).where(Store.owner_id == user.id))).scalars().all()
    return [StoreOut(id=s.id, shopify_domain=s.shopify_domain) for s in rows]


@router.get("/handoffs", response_model=list[HandoffOut])
async def list_handoffs(
    status_filter: str = Query("open", alias="status", pattern="^(open|resolved|all)$"),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Customer requests that need the owner's attention."""
    q = (
        select(SupportHandoff)
        .join(Store, Store.id == SupportHandoff.store_id)
        .where(Store.owner_id == user.id)
        .order_by(SupportHandoff.created_at.desc())
        .limit(100)
    )
    if status_filter != "all":
        q = q.where(SupportHandoff.status == status_filter)
    return (await db.execute(q)).scalars().all()


@router.post("/handoffs/{handoff_id}/resolve", response_model=HandoffOut)
async def resolve_handoff(
    handoff_id: uuid.UUID,
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    h = (
        await db.execute(
            select(SupportHandoff)
            .join(Store, Store.id == SupportHandoff.store_id)
            .where(SupportHandoff.id == handoff_id, Store.owner_id == user.id)
        )
    ).scalar_one_or_none()
    if not h:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Handoff not found")
    h.status = "resolved"
    h.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(h)
    return h
