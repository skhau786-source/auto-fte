# ═══════════════════════════════════════════════════════════════
# domains / chatbot / inbox_service.py
#
# PURPOSE: Support inbox — store owner ki customer conversations
#          (khaas kar woh jo human handoff mein hain) dekhna, reply
#          karna, resolve karna ya bot ko wapas dena.
#
# STATUSES: open (bot sambhal raha hai) | handoff (human chahiye)
#           | closed (resolve)
#
# USED BY: domains/chatbot/inbox_api.py
#
# NOTE:    Har query store_id se scoped hai; API layer pehle store ki
#          ownership check karti hai. (Purane /api/v1/support/* endpoints
#          ownership check nahi karte — inbox unpar nahi bana.)
# ═══════════════════════════════════════════════════════════════

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.sdk.exceptions import AgentError
from src.sdk.models.support import Conversation, Message, HandoffLog

logger = logging.getLogger(__name__)

STATUS_OPEN = "open"
STATUS_HANDOFF = "handoff"
STATUS_CLOSED = "closed"
STATUSES = (STATUS_OPEN, STATUS_HANDOFF, STATUS_CLOSED)

ROLE_CUSTOMER = "customer"
ROLE_HUMAN = "agent_human"

MAX_REPLY_CHARS = 4000


class InboxService:
    """Conversation inbox scoped to one store."""

    def __init__(self, db: AsyncSession, store_id: int):
        self.db = db
        self.store_id = store_id

    # ─── List ───────────────────────────────────────────────────

    async def counts(self) -> dict[str, int]:
        rows = (await self.db.execute(
            select(Conversation.status, func.count(Conversation.id))
            .where(Conversation.store_id == self.store_id)
            .group_by(Conversation.status)
        )).all()
        counts = {s: 0 for s in STATUSES}
        for status, n in rows:
            counts[status] = counts.get(status, 0) + n
        return counts

    async def list_conversations(
        self, status: Optional[str] = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[dict], int]:
        if status and status not in STATUSES:
            raise AgentError(f"Invalid status '{status}'", code=400)

        conditions = [Conversation.store_id == self.store_id]
        if status:
            conditions.append(Conversation.status == status)

        total = (await self.db.execute(
            select(func.count(Conversation.id)).where(*conditions)
        )).scalar() or 0

        stats = (
            select(
                Message.conversation_id.label("cid"),
                func.max(Message.id).label("last_id"),
                func.count(Message.id).label("n"),
                func.max(Message.id).filter(Message.role == ROLE_CUSTOMER).label("last_customer_id"),
                func.max(Message.id).filter(Message.role == ROLE_HUMAN).label("last_human_id"),
            )
            .group_by(Message.conversation_id)
            .subquery()
        )
        last = aliased(Message)
        activity = func.coalesce(last.created_at, Conversation.created_at)

        rows = (await self.db.execute(
            select(Conversation, last, stats.c.n, stats.c.last_customer_id, stats.c.last_human_id)
            .outerjoin(stats, stats.c.cid == Conversation.id)
            .outerjoin(last, last.id == stats.c.last_id)
            .where(*conditions)
            .order_by(activity.desc(), Conversation.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )).all()

        reasons = await self._latest_handoff_reasons([r[0].id for r in rows])

        items = []
        for conv, last_msg, n, last_customer_id, last_human_id in rows:
            items.append({
                "id": conv.id,
                "customer_email": conv.customer_email,
                "status": conv.status,
                "created_at": conv.created_at,
                "last_activity": (last_msg.created_at if last_msg else conv.created_at),
                "last_message": (last_msg.content[:140] if last_msg else ""),
                "last_role": (last_msg.role if last_msg else None),
                # Handoff mein hai aur customer ke aakhri message ke baad owner ne jawab nahi diya
                "awaiting_reply": conv.status == STATUS_HANDOFF and (last_customer_id or 0) > (last_human_id or 0),
                "message_count": int(n or 0),
                "handoff_reason": reasons.get(conv.id),
            })
        return items, total

    async def _latest_handoff_reasons(self, conversation_ids: list[int]) -> dict[int, str]:
        if not conversation_ids:
            return {}
        rows = (await self.db.execute(
            select(HandoffLog.conversation_id, HandoffLog.reason)
            .where(HandoffLog.conversation_id.in_(conversation_ids))
            .order_by(HandoffLog.id)
        )).all()
        return {cid: reason for cid, reason in rows}  # baad wali row pichhli ko override karti hai

    # ─── Thread ─────────────────────────────────────────────────

    async def _get_conversation(self, conversation_id: int, lock: bool = False) -> Conversation:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id, Conversation.store_id == self.store_id
        )
        if lock:
            stmt = stmt.with_for_update()
        conv = (await self.db.execute(stmt)).scalar_one_or_none()
        if conv is None:
            raise AgentError(f"Conversation {conversation_id} not found", code=404)
        return conv

    async def get_thread(self, conversation_id: int) -> dict:
        conv = await self._get_conversation(conversation_id)
        messages = (await self.db.execute(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)
        )).scalars().all()
        handoffs = (await self.db.execute(
            select(HandoffLog).where(HandoffLog.conversation_id == conv.id).order_by(HandoffLog.id.desc())
        )).scalars().all()
        return {
            "id": conv.id,
            "customer_email": conv.customer_email,
            "status": conv.status,
            "created_at": conv.created_at,
            "closed_at": conv.closed_at,
            "messages": [
                {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
                for m in messages
            ],
            "handoffs": [
                {"id": h.id, "reason": h.reason, "assigned_to": h.assigned_to, "created_at": h.created_at}
                for h in handoffs
            ],
        }

    # ─── Actions ────────────────────────────────────────────────

    async def reply(self, conversation_id: int, text: str) -> Message:
        text = (text or "").strip()
        if not text:
            raise AgentError("Reply cannot be empty", code=400)
        if len(text) > MAX_REPLY_CHARS:
            raise AgentError(f"Reply is too long (max {MAX_REPLY_CHARS} characters)", code=400)

        conv = await self._get_conversation(conversation_id, lock=True)
        if conv.status == STATUS_CLOSED:
            raise AgentError("This conversation is closed. Reopen it to reply.", code=409)

        # Owner jawab de raha hai → handoff mein hi rehta hai (bot beech mein nahi bolta);
        # open conversation par reply se woh handoff ban jati hai.
        conv.status = STATUS_HANDOFF
        msg = Message(conversation_id=conv.id, role=ROLE_HUMAN, content=text)
        self.db.add(msg)
        await self.db.commit()
        await self.db.refresh(msg)
        return msg

    async def set_status(self, conversation_id: int, status: str) -> Conversation:
        if status not in STATUSES:
            raise AgentError(f"Invalid status '{status}'", code=400)
        conv = await self._get_conversation(conversation_id, lock=True)
        conv.status = status
        conv.closed_at = datetime.now(timezone.utc) if status == STATUS_CLOSED else None
        await self.db.commit()
        await self.db.refresh(conv)
        return conv
