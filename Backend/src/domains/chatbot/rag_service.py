# ═══════════════════════════════════════════════════════════════
# domains / chatbot / rag_service.py
#
# PURPOSE: RAG business logic — knowledge base + document
#          management, chunking, keyword retrieval, aur LLM prompt
#          ke liye context building.
#
# USED BY: domains/chatbot/rag_api.py
#
# NOTE:    Ported from kulsoom (backend-fte/app/ai/rag_service.py).
#          Fixes: metadata kwarg crash, similarity score ab real
#          (placeholder 1.0 nahi), delete mein chunks sach mein
#          delete hote hain, per-chunk document query hata di.
#          Embeddings abhi nahi — retrieval keyword-overlap hai.
# ═══════════════════════════════════════════════════════════════

import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.sdk.exceptions import AgentError
from src.sdk.models.rag import KnowledgeBase, RagDocument, RagChunk, RagRetrieval

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"\w+", re.UNICODE)


_STOPWORDS = frozenset(
    "a an and are as at be but by can do does did for from had has have how i if in is it "
    "its me my of on or our so that the their them then there these they this to us was we "
    "what when where which who why will with you your".split()
)


def _terms(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _query_terms(query: str) -> set[str]:
    """Query ke meaningful words; agar sab stopwords hon to sab rakho."""
    terms = _terms(query)
    return (terms - _STOPWORDS) or terms


def chunk_text(content: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph/sentence breaks."""
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks: list[str] = []
    pos = 0
    while pos < len(content):
        end = min(pos + chunk_size, len(content))
        if end < len(content):
            for brk in ("\n\n", "\n", ". ", "! ", "? "):
                last = content.rfind(brk, pos, end)
                if last > pos:
                    end = last + len(brk)
                    break

        chunk = content[pos:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(content):
            break
        # Overlap, lekin hamesha aage badho (infinite loop se bachne ke liye)
        pos = max(end - overlap, pos + 1)
    return chunks


class RAGService:
    """Knowledge base operations scoped to one user."""

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id

    # ─── Knowledge Bases ────────────────────────────────────────

    async def create_knowledge_base(
        self,
        name: str,
        description: Optional[str] = None,
        store_id: Optional[int] = None,
        config: Optional[dict] = None,
    ) -> KnowledgeBase:
        kb = KnowledgeBase(
            user_id=self.user_id,
            store_id=store_id,
            name=name,
            description=description,
            config=config or {},
        )
        self.db.add(kb)
        await self.db.commit()
        await self.db.refresh(kb)
        logger.info(f"Knowledge base created: {name} (user={self.user_id})")
        return kb

    async def get_knowledge_base(self, kb_id: int) -> KnowledgeBase:
        result = await self.db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == kb_id,
                KnowledgeBase.user_id == self.user_id,
                KnowledgeBase.is_active == True,  # noqa: E712
            )
        )
        kb = result.scalar_one_or_none()
        if not kb:
            raise AgentError(f"Knowledge base {kb_id} not found", code=404)
        return kb

    async def list_knowledge_bases(self) -> list[KnowledgeBase]:
        result = await self.db.execute(
            select(KnowledgeBase)
            .where(KnowledgeBase.user_id == self.user_id, KnowledgeBase.is_active == True)  # noqa: E712
            .order_by(KnowledgeBase.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_knowledge_base(self, kb_id: int) -> None:
        kb = await self.get_knowledge_base(kb_id)
        await self.db.delete(kb)
        await self.db.commit()

    # ─── Documents ──────────────────────────────────────────────

    async def upload_document(
        self,
        kb_id: int,
        title: str,
        content: str,
        filename: Optional[str] = None,
        file_type: str = "text",
        source_url: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> RagDocument:
        kb = await self.get_knowledge_base(kb_id)
        if not content.strip():
            raise AgentError("Document content is empty", code=400)

        doc = RagDocument(
            knowledge_base_id=kb.id,
            user_id=self.user_id,
            title=title,
            filename=filename,
            file_type=file_type,
            content=content,
            source_url=source_url,
            extra_data=metadata or {},
        )
        self.db.add(doc)
        await self.db.flush()
        await self._index_document(doc, kb)
        await self.db.commit()
        await self.db.refresh(doc)
        logger.info(f"Document uploaded: {title} → KB {kb_id} ({doc.chunk_count} chunks)")
        return doc

    async def get_document(self, doc_id: int) -> RagDocument:
        result = await self.db.execute(
            select(RagDocument).where(
                RagDocument.id == doc_id,
                RagDocument.user_id == self.user_id,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise AgentError(f"Document {doc_id} not found", code=404)
        return doc

    async def list_documents(self, kb_id: int) -> list[RagDocument]:
        kb = await self.get_knowledge_base(kb_id)
        result = await self.db.execute(
            select(RagDocument)
            .where(RagDocument.knowledge_base_id == kb.id)
            .order_by(RagDocument.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_document(self, doc_id: int) -> None:
        doc = await self.get_document(doc_id)
        kb = await self.get_knowledge_base(doc.knowledge_base_id)

        kb.document_count = max(0, (kb.document_count or 0) - 1)
        kb.chunk_count = max(0, (kb.chunk_count or 0) - (doc.chunk_count or 0))
        kb.total_tokens = max(0, (kb.total_tokens or 0) - (doc.token_count or 0))

        await self.db.delete(doc)  # chunks cascade se delete hote hain
        await self.db.commit()
        logger.info(f"Document deleted: {doc_id}")

    # ─── Indexing ───────────────────────────────────────────────

    async def _index_document(self, doc: RagDocument, kb: KnowledgeBase) -> None:
        now = datetime.now(timezone.utc)
        pieces = chunk_text(doc.content)

        total_tokens = 0
        for idx, text in enumerate(pieces):
            tokens = len(text) // 4  # rough estimate: 4 chars ≈ 1 token
            total_tokens += tokens
            self.db.add(RagChunk(
                document_id=doc.id,
                knowledge_base_id=kb.id,
                chunk_index=idx,
                content=text,
                token_count=tokens,
                extra_data={"source_doc": doc.title},
                is_indexed=True,
                indexed_at=now,
            ))

        doc.chunk_count = len(pieces)
        doc.token_count = total_tokens
        doc.is_indexed = True
        doc.indexed_at = now

        kb.document_count = (kb.document_count or 0) + 1
        kb.chunk_count = (kb.chunk_count or 0) + len(pieces)
        kb.total_tokens = (kb.total_tokens or 0) + total_tokens
        kb.is_indexed = True
        kb.last_indexed_at = now

    # ─── Retrieval ──────────────────────────────────────────────

    async def retrieve(self, kb_id: int, query: str, top_k: int = 5, min_score: float = 0.0) -> dict:
        """Keyword-overlap retrieval. score = matched query terms / query terms."""
        kb = await self.get_knowledge_base(kb_id)
        started = time.perf_counter()

        query_terms = _query_terms(query)
        scored: list[tuple[RagChunk, str, float]] = []
        if query_terms:
            result = await self.db.execute(
                select(RagChunk, RagDocument.title)
                .join(RagDocument, RagDocument.id == RagChunk.document_id)
                .where(RagChunk.knowledge_base_id == kb.id, RagChunk.is_indexed == True)  # noqa: E712
            )
            for chunk, title in result.all():
                score = len(query_terms & _terms(chunk.content)) / len(query_terms)
                if score > 0 and score >= min_score:
                    scored.append((chunk, title, score))
            scored.sort(key=lambda x: x[2], reverse=True)
            scored = scored[:top_k]

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        self.db.add(RagRetrieval(
            user_id=self.user_id,
            knowledge_base_id=kb.id,
            query=query,
            retrieved_chunk_ids=[c.id for c, _, _ in scored],
            similarity_scores=[round(s, 4) for _, _, s in scored],
            retrieved_count=len(scored),
            retrieval_time_ms=elapsed_ms,
        ))
        await self.db.commit()

        return {
            "query": query,
            "knowledge_base_id": kb.id,
            "chunks_retrieved": len(scored),
            "chunks": [
                {
                    "id": c.id,
                    "document_id": c.document_id,
                    "document_title": title,
                    "content": c.content,
                    "chunk_index": c.chunk_index,
                    "similarity_score": round(score, 4),
                }
                for c, title, score in scored
            ],
            "retrieval_time_ms": elapsed_ms,
        }

    async def build_rag_context(self, kb_id: int, query: str, top_k: int = 5) -> dict:
        """Context string jo LLM prompt mein lag sakti hai."""
        result = await self.retrieve(kb_id=kb_id, query=query, top_k=top_k)
        chunks = result["chunks"]
        if not chunks:
            return {"context": "", "source_documents": 0, "tokens_added": 0}

        parts = [f"Retrieved {len(chunks)} relevant passages:"]
        for i, c in enumerate(chunks, 1):
            parts.append(f"\n[Source {i}: {c['document_title']}]\n{c['content']}")
        parts.append("\n\nAnswer based on the above context:")
        context = "\n".join(parts)

        return {
            "context": context,
            "source_documents": len({c["document_id"] for c in chunks}),
            "tokens_added": len(context) // 4,
        }
