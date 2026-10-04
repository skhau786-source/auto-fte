# ═══════════════════════════════════════════════════════════════
# domains / chatbot / rag_api.py
#
# PURPOSE: Knowledge-base (RAG) endpoints. Sab authenticated.
#
#   POST   /chatbot/rag/knowledge-bases
#   GET    /chatbot/rag/knowledge-bases
#   GET    /chatbot/rag/knowledge-bases/{kb_id}
#   DELETE /chatbot/rag/knowledge-bases/{kb_id}
#   POST   /chatbot/rag/knowledge-bases/{kb_id}/documents
#   GET    /chatbot/rag/knowledge-bases/{kb_id}/documents
#   DELETE /chatbot/rag/documents/{doc_id}
#   POST   /chatbot/rag/knowledge-bases/{kb_id}/search
#   POST   /chatbot/rag/knowledge-bases/{kb_id}/augment
#
# NOTE:    Ported from kulsoom (backend-fte/app/ai/rag_router.py).
#          Document content ab JSON body mein aata hai (query
#          string mein nahi).
# ═══════════════════════════════════════════════════════════════

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.sdk.database import get_db
from src.sdk.exceptions import AgentError
from src.domains.auth.models import User
from src.domains.auth.service import get_current_user
from src.domains.chatbot.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chatbot/rag", tags=["Chatbot RAG"])


# ─── Schemas ──────────────────────────────────────────────────

class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    store_id: Optional[int] = None


class KnowledgeBaseOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    store_id: Optional[int]
    document_count: int
    chunk_count: int
    total_tokens: int
    is_indexed: bool
    last_indexed_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    filename: Optional[str] = None
    file_type: str = "text"
    source_url: Optional[str] = None
    metadata: Optional[dict] = None


class DocumentOut(BaseModel):
    id: int
    knowledge_base_id: int
    title: str
    filename: Optional[str]
    file_type: str
    chunk_count: int
    token_count: int
    is_indexed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SearchChunk(BaseModel):
    id: int
    document_id: int
    document_title: str
    content: str
    chunk_index: int
    similarity_score: float


class SearchResponse(BaseModel):
    query: str
    knowledge_base_id: int
    chunks_retrieved: int
    chunks: list[SearchChunk]
    retrieval_time_ms: int


class ContextResponse(BaseModel):
    context: str
    source_documents: int
    tokens_added: int


def _http_error(exc: AgentError) -> HTTPException:
    code = exc.code if exc.code in (400, 404) else status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail=exc.message)


# ─── Knowledge Bases ──────────────────────────────────────────

@router.post("/knowledge-bases", response_model=KnowledgeBaseOut, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RAGService(db, user.id)
    return await service.create_knowledge_base(
        name=payload.name, description=payload.description, store_id=payload.store_id
    )


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseOut])
async def list_knowledge_bases(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await RAGService(db, user.id).list_knowledge_bases()


@router.get("/knowledge-bases/{kb_id}", response_model=KnowledgeBaseOut)
async def get_knowledge_base(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await RAGService(db, user.id).get_knowledge_base(kb_id)
    except AgentError as exc:
        raise _http_error(exc)


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await RAGService(db, user.id).delete_knowledge_base(kb_id)
    except AgentError as exc:
        raise _http_error(exc)
    return {"message": "Knowledge base deleted"}


# ─── Documents ────────────────────────────────────────────────

@router.post("/knowledge-bases/{kb_id}/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    kb_id: int,
    payload: DocumentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await RAGService(db, user.id).upload_document(
            kb_id=kb_id,
            title=payload.title,
            content=payload.content,
            filename=payload.filename,
            file_type=payload.file_type,
            source_url=payload.source_url,
            metadata=payload.metadata,
        )
    except AgentError as exc:
        raise _http_error(exc)


@router.get("/knowledge-bases/{kb_id}/documents", response_model=list[DocumentOut])
async def list_documents(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await RAGService(db, user.id).list_documents(kb_id)
    except AgentError as exc:
        raise _http_error(exc)


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await RAGService(db, user.id).delete_document(doc_id)
    except AgentError as exc:
        raise _http_error(exc)
    return {"message": "Document deleted"}


# ─── Search / Augment ─────────────────────────────────────────

@router.post("/knowledge-bases/{kb_id}/search", response_model=SearchResponse)
async def search_knowledge_base(
    kb_id: int,
    query: str = Query(..., min_length=1, max_length=1000),
    top_k: int = Query(5, ge=1, le=20),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await RAGService(db, user.id).retrieve(kb_id=kb_id, query=query, top_k=top_k)
    except AgentError as exc:
        raise _http_error(exc)


@router.post("/knowledge-bases/{kb_id}/augment", response_model=ContextResponse)
async def build_rag_context(
    kb_id: int,
    query: str = Query(..., min_length=1, max_length=1000),
    top_k: int = Query(5, ge=1, le=20),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await RAGService(db, user.id).build_rag_context(kb_id=kb_id, query=query, top_k=top_k)
    except AgentError as exc:
        raise _http_error(exc)
