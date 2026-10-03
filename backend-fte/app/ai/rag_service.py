"""
RAG Service — Retrieval-Augmented Generation business logic.

Handles:
- Document uploading and chunking
- Vector embedding generation and indexing
- Semantic search and retrieval
- RAG context augmentation for LLM prompts
"""

import uuid
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.ai.rag_models import KnowledgeBase, RAGDocument, RAGChunk, RAGRetrieval
from app.ai.llm_client import get_llm_client
from app.ai.exceptions import AgentError

logger = logging.getLogger(__name__)


class RAGService:
    """
    Orchestrates RAG operations: document management, indexing, and retrieval.
    """

    def __init__(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ):
        self.db = db
        self.organization_id = organization_id
        self.user_id = user_id
        self.logger = logging.getLogger(f"{__name__}.RAGService")

    # ═══════════════════════════════════════════════════════════════════
    # KNOWLEDGE BASE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════

    async def create_knowledge_base(
        self,
        name: str,
        description: Optional[str] = None,
        embedding_model: str = "openai/text-embedding-3-small",
        config: Optional[dict] = None,
    ) -> KnowledgeBase:
        """Create a new knowledge base for the organization."""
        kb = KnowledgeBase(
            organization_id=self.organization_id,
            name=name,
            description=description,
            embedding_model=embedding_model,
            config=config or {},
            created_by=self.user_id,
        )
        self.db.add(kb)
        await self.db.commit()
        await self.db.refresh(kb)
        self.logger.info("Knowledge base created: %s (org=%s)", name, self.organization_id)
        return kb

    async def get_knowledge_base(self, kb_id: uuid.UUID) -> KnowledgeBase:
        """Get a knowledge base by ID."""
        result = await self.db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == kb_id,
                KnowledgeBase.organization_id == self.organization_id,
            )
        )
        kb = result.scalar_one_or_none()
        if not kb:
            raise AgentError(
                message=f"Knowledge base {kb_id} not found",
                detail={"error_code": "KB_NOT_FOUND"},
            )
        return kb

    async def list_knowledge_bases(self) -> list[KnowledgeBase]:
        """List all knowledge bases for the organization."""
        result = await self.db.execute(
            select(KnowledgeBase)
            .where(
                KnowledgeBase.organization_id == self.organization_id,
                KnowledgeBase.is_active == True,  # noqa: E712
            )
            .order_by(KnowledgeBase.created_at.desc())
        )
        return list(result.scalars().all())

    # ═══════════════════════════════════════════════════════════════════
    # DOCUMENT MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════

    async def upload_document(
        self,
        kb_id: uuid.UUID,
        title: str,
        content: str,
        filename: Optional[str] = None,
        file_type: str = "text",
        source_url: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> RAGDocument:
        """Upload a document to a knowledge base."""
        kb = await self.get_knowledge_base(kb_id)

        doc = RAGDocument(
            knowledge_base_id=kb_id,
            organization_id=self.organization_id,
            title=title,
            filename=filename,
            file_type=file_type,
            content=content,
            source_url=source_url,
            metadata=metadata or {},
            uploaded_by=self.user_id,
        )
        self.db.add(doc)
        await self.db.commit()
        await self.db.refresh(doc)

        # Auto-index the document
        await self._index_document(doc, kb)

        self.logger.info("Document uploaded: %s to KB %s", title, kb_id)
        return doc

    async def get_document(self, doc_id: uuid.UUID) -> RAGDocument:
        """Get a document by ID."""
        result = await self.db.execute(
            select(RAGDocument).where(
                RAGDocument.id == doc_id,
                RAGDocument.organization_id == self.organization_id,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise AgentError(
                message=f"Document {doc_id} not found",
                detail={"error_code": "DOC_NOT_FOUND"},
            )
        return doc

    async def list_documents(self, kb_id: uuid.UUID) -> list[RAGDocument]:
        """List all documents in a knowledge base."""
        result = await self.db.execute(
            select(RAGDocument)
            .where(RAGDocument.knowledge_base_id == kb_id)
            .order_by(RAGDocument.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_document(self, doc_id: uuid.UUID) -> None:
        """Delete a document and its chunks."""
        doc = await self.get_document(doc_id)
        kb = await self.get_knowledge_base(doc.knowledge_base_id)

        # Delete chunks
        await self.db.execute(
            select(RAGChunk).where(RAGChunk.document_id == doc_id)
        )
        await self.db.delete(doc)
        await self.db.commit()

        # Update KB stats
        kb.document_count = max(0, kb.document_count - 1)
        kb.chunk_count = max(0, kb.chunk_count - doc.chunk_count)
        kb.total_tokens = max(0, kb.total_tokens - doc.token_count)
        await self.db.commit()

        self.logger.info("Document deleted: %s", doc_id)

    # ═══════════════════════════════════════════════════════════════════
    # DOCUMENT INDEXING & CHUNKING
    # ═══════════════════════════════════════════════════════════════════

    async def _index_document(self, doc: RAGDocument, kb: KnowledgeBase) -> None:
        """
        Index a document: chunk it and generate embeddings.

        This is called automatically when a document is uploaded.
        """
        try:
            # 1. Chunk the document
            chunks = await self._chunk_document(doc.content)

            # 2. Generate embeddings for each chunk
            llm_client = get_llm_client()
            chunk_objs = []

            for idx, chunk_text in enumerate(chunks):
                # Get embedding
                embedding = await self._get_embedding(chunk_text, kb.embedding_model)

                # Count tokens (rough estimate: 4 chars ≈ 1 token)
                token_count = len(chunk_text) // 4

                chunk_obj = RAGChunk(
                    document_id=doc.id,
                    knowledge_base_id=kb.id,
                    organization_id=self.organization_id,
                    chunk_index=idx,
                    content=chunk_text,
                    token_count=token_count,
                    embedding=embedding,
                    embedding_model=kb.embedding_model,
                    metadata={
                        "source_doc": doc.title,
                        "char_position": sum(len(c) for c in chunks[:idx]),
                    },
                    is_indexed=True,
                    indexed_at=datetime.now(timezone.utc),
                )
                chunk_objs.append(chunk_obj)
                self.db.add(chunk_obj)

            # 3. Update document stats
            doc.chunk_count = len(chunks)
            doc.token_count = sum(c.token_count for c in chunk_objs)
            doc.is_indexed = True
            doc.indexed_at = datetime.now(timezone.utc)

            # 4. Update KB stats
            kb.document_count += 1
            kb.chunk_count += len(chunks)
            kb.total_tokens += doc.token_count
            kb.last_indexed_at = datetime.now(timezone.utc)

            await self.db.commit()

            self.logger.info(
                "Document indexed: %s (%d chunks, %d tokens)",
                doc.title, len(chunks), doc.token_count,
            )
        except Exception as exc:
            self.logger.error("Failed to index document %s: %s", doc.id, exc)
            raise

    async def _chunk_document(self, content: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
        """
        Split document content into overlapping chunks.

        Args:
            content: The full document text
            chunk_size: Target characters per chunk
            overlap: Character overlap between consecutive chunks

        Returns:
            List of text chunks
        """
        chunks = []
        pos = 0

        while pos < len(content):
            # Find chunk end (try to break at sentence boundary)
            end = min(pos + chunk_size, len(content))

            if end < len(content):
                # Try to break at a sentence or paragraph boundary
                for break_char in ['\n\n', '\n', '. ', '! ', '? ']:
                    last_break = content.rfind(break_char, pos, end)
                    if last_break > pos:
                        end = last_break + len(break_char)
                        break

            chunk = content[pos:end].strip()
            if chunk:
                chunks.append(chunk)

            # Move forward with overlap
            pos = end - overlap if end < len(content) else len(content)

        return chunks

    async def _get_embedding(self, text: str, model: str) -> Optional[bytes]:
        """
        Get vector embedding for text using LLM client.

        This is a placeholder — in production, use a proper embedding service.
        """
        try:
            # This would typically call an embedding API
            # For now, we return None and handle sparse vectors
            # In production: use OpenAI, Cohere, or local embeddings
            logger.info("Generating embedding for text chunk (model=%s)", model)
            # Placeholder: return None for now
            # Real implementation would call embedding API
            return None
        except Exception as exc:
            logger.warning("Failed to generate embedding: %s", exc)
            return None

    # ═══════════════════════════════════════════════════════════════════
    # SEMANTIC SEARCH & RETRIEVAL
    # ═══════════════════════════════════════════════════════════════════

    async def retrieve(
        self,
        kb_id: uuid.UUID,
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        task_id: Optional[uuid.UUID] = None,
        agent_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """
        Retrieve relevant chunks from a knowledge base using semantic search.

        Args:
            kb_id: Knowledge base ID
            query: Search query
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score
            task_id: Optional task ID for audit trail
            agent_id: Optional agent ID for context

        Returns:
            Dictionary with retrieved chunks and metadata
        """
        kb = await self.get_knowledge_base(kb_id)
        start_time = datetime.now(timezone.utc)

        try:
            # Get query embedding
            query_embedding = await self._get_embedding(query, kb.embedding_model)

            # For now, use BM25-style keyword search as fallback
            # In production, use vector similarity (cosine distance)
            chunks = await self._keyword_search(kb_id, query, top_k)

            # Log retrieval
            await self._log_retrieval(
                kb_id=kb_id,
                query=query,
                retrieved_chunk_ids=[str(c.id) for c in chunks],
                similarity_scores=[1.0] * len(chunks),  # Placeholder
                task_id=task_id,
                agent_id=agent_id,
                retrieval_time_ms=int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
            )

            return {
                "status": "success",
                "query": query,
                "knowledge_base_id": str(kb_id),
                "chunks_retrieved": len(chunks),
                "chunks": [
                    {
                        "id": str(c.id),
                        "document_id": str(c.document_id),
                        "document_title": (await self.get_document(c.document_id)).title,
                        "content": c.content,
                        "chunk_index": c.chunk_index,
                        "similarity_score": 1.0,  # Placeholder
                        "metadata": c.metadata or {},
                    }
                    for c in chunks
                ],
                "retrieval_time_ms": int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
            }
        except Exception as exc:
            logger.error("Retrieval failed: %s", exc)
            return {
                "status": "error",
                "error": str(exc),
                "chunks": [],
            }

    async def _keyword_search(
        self,
        kb_id: uuid.UUID,
        query: str,
        top_k: int = 5,
    ) -> list[RAGChunk]:
        """
        Simple keyword-based search (BM25-style fallback).

        In production, replace with vector similarity using pgvector.
        """
        query_terms = set(query.lower().split())

        # Fetch all chunks from KB
        result = await self.db.execute(
            select(RAGChunk).where(
                RAGChunk.knowledge_base_id == kb_id,
                RAGChunk.is_indexed == True,  # noqa: E712
            )
        )
        chunks = list(result.scalars().all())

        # Score by term overlap
        scored_chunks = []
        for chunk in chunks:
            chunk_terms = set(chunk.content.lower().split())
            overlap = len(query_terms & chunk_terms)
            if overlap > 0:
                scored_chunks.append((chunk, overlap / len(query_terms)))

        # Sort by score descending
        scored_chunks.sort(key=lambda x: x[1], reverse=True)

        return [c[0] for c in scored_chunks[:top_k]]

    async def _log_retrieval(
        self,
        kb_id: uuid.UUID,
        query: str,
        retrieved_chunk_ids: list[str],
        similarity_scores: list[float],
        task_id: Optional[uuid.UUID] = None,
        agent_id: Optional[uuid.UUID] = None,
        retrieval_time_ms: int = 0,
    ) -> RAGRetrieval:
        """Log a retrieval event for audit and analytics."""
        retrieval = RAGRetrieval(
            organization_id=self.organization_id,
            knowledge_base_id=kb_id,
            query=query,
            retrieved_chunk_ids=retrieved_chunk_ids,
            similarity_scores=similarity_scores,
            retrieved_count=len(retrieved_chunk_ids),
            retrieval_time_ms=retrieval_time_ms,
            task_id=task_id,
            agent_id=agent_id,
            requested_by=self.user_id,
        )
        self.db.add(retrieval)
        await self.db.flush()
        return retrieval

    # ═══════════════════════════════════════════════════════════════════
    # RAG CONTEXT AUGMENTATION
    # ═══════════════════════════════════════════════════════════════════

    async def build_rag_context(
        self,
        kb_id: uuid.UUID,
        query: str,
        top_k: int = 5,
    ) -> str:
        """
        Build a context string from retrieved documents for LLM augmentation.

        Returns formatted context that can be prepended to LLM prompts.
        """
        result = await self.retrieve(
            kb_id=kb_id,
            query=query,
            top_k=top_k,
        )

        if result["status"] != "success":
            return ""

        # Format chunks for context
        context_parts = [f"Retrieved {len(result['chunks'])} relevant documents:\n"]

        for i, chunk in enumerate(result["chunks"], 1):
            context_parts.append(f"\n[Document {i}: {chunk['document_title']}]")
            context_parts.append(f"Content: {chunk['content'][:500]}...")  # Truncate for length

        context_parts.append("\n\nAnswer based on the above context:")

        return "\n".join(context_parts)
