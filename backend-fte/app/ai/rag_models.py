"""
RAG System Models — Retrieval-Augmented Generation data structures.

Tables:
- knowledge_bases: Document collections per organization
- rag_documents: Documents with metadata
- rag_chunks: Text chunks with vector embeddings
- rag_embeddings: Cached embeddings for semantic search
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Boolean, DateTime, ForeignKey, Enum, func, Text, Integer, Float,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, VECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class KnowledgeBase(Base):
    """Collection of documents for a specific organization."""
    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Configuration for this knowledge base
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Embedding model used for this KB
    embedding_model: Mapped[str] = mapped_column(String(255), default="openai/text-embedding-3-small")

    # Indexing status
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Statistics
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    documents: Mapped[list["RAGDocument"]] = relationship(
        "RAGDocument",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
        foreign_keys="[RAGDocument.knowledge_base_id]",
    )


class RAGDocument(Base):
    """A document uploaded to a knowledge base."""
    __tablename__ = "rag_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Document metadata
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_type: Mapped[str] = mapped_column(String(50), default="text")  # pdf, txt, md, html, etc.

    # Content
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Processing metadata
    metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Chunking info
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    # Status
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    knowledge_base: Mapped["KnowledgeBase"] = relationship(
        "KnowledgeBase",
        back_populates="documents",
        foreign_keys=[knowledge_base_id],
    )
    chunks: Mapped[list["RAGChunk"]] = relationship(
        "RAGChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="[RAGChunk.document_id]",
    )


class RAGChunk(Base):
    """A chunk of text from a document with vector embedding."""
    __tablename__ = "rag_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rag_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Chunk content and metadata
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)  # Position in document
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    # Vector embedding (pgvector format: vector of floats)
    embedding: Mapped[Optional[bytes]] = mapped_column(VECTOR(1536), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=True)

    # Metadata
    metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Context pointers for retrieval
    previous_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    next_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    document: Mapped["RAGDocument"] = relationship(
        "RAGDocument",
        back_populates="chunks",
        foreign_keys=[document_id],
    )


class RAGRetrieval(Base):
    """Audit trail for RAG retrievals — tracks what was retrieved and when."""
    __tablename__ = "rag_retrievals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Query and retrieval metadata
    query: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_chunk_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Performance metrics
    retrieval_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    similarity_scores: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    retrieved_count: Mapped[int] = mapped_column(Integer, default=0)

    # Context
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_agent_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
