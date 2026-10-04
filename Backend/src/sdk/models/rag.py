# ═══════════════════════════════════════════════════════════════
# fte_sdk / models / rag.py
#
# PURPOSE: RAG (knowledge base) models — owner ki documents ko
#          chunks mein tod kar store karte hain taake chatbot
#          unse answer de sake.
#
# TABLES:  knowledge_bases, rag_documents, rag_chunks, rag_retrievals
# USED BY: domains/chatbot/rag_service.py, rag_api.py
#
# NOTE:    Ported from kulsoom branch (backend-fte/app/ai/rag_models.py).
#          UUID/organization ids → int user_id/store_id. Embedding
#          column nahi hai kyun ke kulsoom ka embedding sirf
#          placeholder tha; retrieval keyword-overlap par chalti hai.
# ═══════════════════════════════════════════════════════════════

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    ForeignKey, JSON, func,
)
from sqlalchemy.orm import relationship

from src.sdk.database import Base


# ─── KnowledgeBase ────────────────────────────────────────────
# Documents ka collection. Owner = auth User; optional Store scope.

class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True, index=True)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    config = Column(JSON, nullable=True)

    is_indexed = Column(Boolean, default=False)
    last_indexed_at = Column(DateTime(timezone=True), nullable=True)

    document_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    documents = relationship("RagDocument", back_populates="knowledge_base", cascade="all, delete-orphan")


# ─── RagDocument ──────────────────────────────────────────────

class RagDocument(Base):
    __tablename__ = "rag_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    filename = Column(String(500), nullable=True)
    file_type = Column(String(50), default="text")          # text | md | html | pdf ...
    content = Column(Text, nullable=False)
    source_url = Column(String(500), nullable=True)
    extra_data = Column(JSON, nullable=True)

    chunk_count = Column(Integer, default=0)
    token_count = Column(Integer, default=0)
    is_indexed = Column(Boolean, default=False)
    indexed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    chunks = relationship("RagChunk", back_populates="document", cascade="all, delete-orphan")


# ─── RagChunk ─────────────────────────────────────────────────

class RagChunk(Base):
    __tablename__ = "rag_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)

    chunk_index = Column(Integer, nullable=False)           # Position in document
    content = Column(Text, nullable=False)
    token_count = Column(Integer, default=0)
    extra_data = Column(JSON, nullable=True)

    is_indexed = Column(Boolean, default=False)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("RagDocument", back_populates="chunks")


# ─── RagRetrieval ─────────────────────────────────────────────
# Audit trail: kis query par kaunse chunks mile.

class RagRetrieval(Base):
    __tablename__ = "rag_retrievals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)

    query = Column(Text, nullable=False)
    retrieved_chunk_ids = Column(JSON, nullable=True)
    similarity_scores = Column(JSON, nullable=True)
    retrieved_count = Column(Integer, default=0)
    retrieval_time_ms = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
