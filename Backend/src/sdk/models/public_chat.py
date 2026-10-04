# ═══════════════════════════════════════════════════════════════
# fte_sdk / models / public_chat.py
#
# PURPOSE: Public website chat — store ki public key aur anjaan
#          visitors ke anonymous sessions.
#
# TABLES:  store_public_keys, visitor_sessions
# USED BY: domains/chatbot/public_chat_service.py, public_chat_api.py
#
# NOTE:    Naye tables hain (stores table mein column nahi) taake
#          maujooda databases par ALTER ke bina create_all chal jaye.
# ═══════════════════════════════════════════════════════════════

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func

from src.sdk.database import Base


# ─── StorePublicKey ───────────────────────────────────────────
# Website widget ki pehchan (data-store-key). Secret nahi hai (page source mein dikhti hai),
# lekin andaza lagana mushkil hai. Rotate karne par purani key bekaar ho jati hai.

class StorePublicKey(Base):
    __tablename__ = "store_public_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    public_key = Column(String(64), nullable=False, unique=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    rotated_at = Column(DateTime(timezone=True), nullable=True)


# ─── VisitorSession ───────────────────────────────────────────
# Har anjaan visitor ka session. Token sirf visitor ke paas hai; DB mein sirf SHA-256 hash.
# Ek session = ek conversation, isliye visitor sirf apni chat dekh sakta hai.

class VisitorSession(Base):
    __tablename__ = "visitor_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
