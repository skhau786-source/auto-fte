"""
RAG Router — API endpoints for Retrieval-Augmented Generation.

Endpoints:
POST   /ai/rag/knowledge-bases              — Create knowledge base
GET    /ai/rag/knowledge-bases              — List knowledge bases
GET    /ai/rag/knowledge-bases/{id}         — Get knowledge base details
DELETE /ai/rag/knowledge-bases/{id}         — Delete knowledge base

POST   /ai/rag/kb/{kb_id}/documents        — Upload document
GET    /ai/rag/kb/{kb_id}/documents        — List documents
GET    /ai/rag/documents/{doc_id}          — Get document details
DELETE /ai/rag/documents/{doc_id}          — Delete document

POST   /ai/rag/kb/{kb_id}/search           — Semantic search
POST   /ai/rag/kb/{kb_id}/augment          — Build RAG context for LLM

POST   /ai/tasks/{task_id}/rag-retrieve    — Retrieve for a task with RAG
"""

import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent
from app.organizations.models import Organization
from app.ai.dependencies import require_agent_manage
from app.ai.rag_service import RAGService
from app.ai.rag_models import KnowledgeBase, RAGDocument
from app.ai.exceptions import AgentError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/rag", tags=["RAG"])


# ═══════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════

from pydantic import BaseModel

class KnowledgeBaseCreateRequest(BaseModel):
    name: str
    description: str | None = None
    embedding_model: str = "openai/text-embedding-3-small"

class KnowledgeBaseOut(BaseModel):
    id: str
    organization_id: str
    name: str
    description: str | None
    document_count: int
    chunk_count: int
    total_tokens: int
    is_indexed: bool
    last_indexed_at: str | None
    created_at: str
    updated_at: str

class DocumentUploadRequest(BaseModel):
    title: str
    content: str
    source_url: str | None = None
    metadata: dict | None = None

class DocumentOut(BaseModel):
    id: str
    knowledge_base_id: str
    title: str
    filename: str | None
    file_type: str
    chunk_count: int
    token_count: int
    is_indexed: bool
    created_at: str

class SearchResultChunk(BaseModel):
    id: str
    document_id: str
    document_title: str
    content: str
    chunk_index: int
    similarity_score: float

class SearchResponse(BaseModel):
    status: str
    query: str
    knowledge_base_id: str
    chunks_retrieved: int
    chunks: list[SearchResultChunk]
    retrieval_time_ms: int

class RAGContextResponse(BaseModel):
    status: str
    context: str
    source_documents: int
    tokens_added: int


# ═══════════════════════════════════════════════════════════════════
# Knowledge Base Endpoints
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/knowledge-bases",
    status_code=status.HTTP_201_CREATED,
    response_model=KnowledgeBaseOut,
    summary="Create knowledge base",
)
async def create_knowledge_base(
    payload: KnowledgeBaseCreateRequest,
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new knowledge base for document storage and RAG."""
    try:
        service = RAGService(db=db, organization_id=org.id, user_id=user.id)
        kb = await service.create_knowledge_base(
            name=payload.name,
            description=payload.description,
            embedding_model=payload.embedding_model,
        )
        return KnowledgeBaseOut(
            id=str(kb.id),
            organization_id=str(kb.organization_id),
            name=kb.name,
            description=kb.description,
            document_count=kb.document_count,
            chunk_count=kb.chunk_count,
            total_tokens=kb.total_tokens,
            is_indexed=kb.is_indexed,
            last_indexed_at=kb.last_indexed_at.isoformat() if kb.last_indexed_at else None,
            created_at=kb.created_at.isoformat(),
            updated_at=kb.updated_at.isoformat(),
        )
    except AgentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": exc.message, **exc.detail},
        )


@router.get(
    "/knowledge-bases",
    response_model=dict,
    summary="List knowledge bases",
)
async def list_knowledge_bases(
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all knowledge bases in the organization."""
    service = RAGService(db=db, organization_id=org.id, user_id=user.id)
    kbs = await service.list_knowledge_bases()
    return {
        "items": [
            KnowledgeBaseOut(
                id=str(kb.id),
                organization_id=str(kb.organization_id),
                name=kb.name,
                description=kb.description,
                document_count=kb.document_count,
                chunk_count=kb.chunk_count,
                total_tokens=kb.total_tokens,
                is_indexed=kb.is_indexed,
                last_indexed_at=kb.last_indexed_at.isoformat() if kb.last_indexed_at else None,
                created_at=kb.created_at.isoformat(),
                updated_at=kb.updated_at.isoformat(),
            )
            for kb in kbs
        ],
        "total": len(kbs),
    }


@router.get(
    "/knowledge-bases/{kb_id}",
    response_model=KnowledgeBaseOut,
    summary="Get knowledge base details",
)
async def get_knowledge_base(
    kb_id: uuid.UUID,
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific knowledge base."""
    try:
        service = RAGService(db=db, organization_id=org.id, user_id=user.id)
        kb = await service.get_knowledge_base(kb_id)
        return KnowledgeBaseOut(
            id=str(kb.id),
            organization_id=str(kb.organization_id),
            name=kb.name,
            description=kb.description,
            document_count=kb.document_count,
            chunk_count=kb.chunk_count,
            total_tokens=kb.total_tokens,
            is_indexed=kb.is_indexed,
            last_indexed_at=kb.last_indexed_at.isoformat() if kb.last_indexed_at else None,
            created_at=kb.created_at.isoformat(),
            updated_at=kb.updated_at.isoformat(),
        )
    except AgentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)


# ═══════════════════════════════════════════════════════════════════
# Document Endpoints
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/kb/{kb_id}/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentOut,
    summary="Upload document to knowledge base",
)
async def upload_document(
    kb_id: uuid.UUID,
    title: str = Query(..., description="Document title"),
    content: str = Query(..., description="Document content"),
    source_url: str | None = Query(None),
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document to a knowledge base for indexing and retrieval."""
    try:
        service = RAGService(db=db, organization_id=org.id, user_id=user.id)
        doc = await service.upload_document(
            kb_id=kb_id,
            title=title,
            content=content,
            source_url=source_url,
        )
        return DocumentOut(
            id=str(doc.id),
            knowledge_base_id=str(doc.knowledge_base_id),
            title=doc.title,
            filename=doc.filename,
            file_type=doc.file_type,
            chunk_count=doc.chunk_count,
            token_count=doc.token_count,
            is_indexed=doc.is_indexed,
            created_at=doc.created_at.isoformat(),
        )
    except AgentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": exc.message},
        )


@router.get(
    "/kb/{kb_id}/documents",
    response_model=dict,
    summary="List documents in knowledge base",
)
async def list_documents(
    kb_id: uuid.UUID,
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all documents in a knowledge base."""
    try:
        service = RAGService(db=db, organization_id=org.id, user_id=user.id)
        docs = await service.list_documents(kb_id)
        return {
            "items": [
                DocumentOut(
                    id=str(d.id),
                    knowledge_base_id=str(d.knowledge_base_id),
                    title=d.title,
                    filename=d.filename,
                    file_type=d.file_type,
                    chunk_count=d.chunk_count,
                    token_count=d.token_count,
                    is_indexed=d.is_indexed,
                    created_at=d.created_at.isoformat(),
                )
                for d in docs
            ],
            "total": len(docs),
        }
    except AgentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)


@router.delete(
    "/documents/{doc_id}",
    summary="Delete document",
)
async def delete_document(
    doc_id: uuid.UUID,
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document and its indexed chunks."""
    try:
        service = RAGService(db=db, organization_id=org.id, user_id=user.id)
        await service.delete_document(doc_id)
        return {"message": "Document deleted successfully"}
    except AgentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)


# ═══════════════════════════════════════════════════════════════════
# Search & Retrieval Endpoints
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/kb/{kb_id}/search",
    response_model=SearchResponse,
    summary="Semantic search in knowledge base",
)
async def search_knowledge_base(
    kb_id: uuid.UUID,
    query: str = Query(..., description="Search query"),
    top_k: int = Query(5, ge=1, le=20, description="Number of results"),
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search for relevant documents using semantic search."""
    try:
        service = RAGService(db=db, organization_id=org.id, user_id=user.id)
        result = await service.retrieve(
            kb_id=kb_id,
            query=query,
            top_k=top_k,
        )

        if result["status"] != "success":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": result.get("error", "Search failed")},
            )

        return SearchResponse(
            status="success",
            query=query,
            knowledge_base_id=str(kb_id),
            chunks_retrieved=result["chunks_retrieved"],
            chunks=[
                SearchResultChunk(
                    id=c["id"],
                    document_id=c["document_id"],
                    document_title=c["document_title"],
                    content=c["content"],
                    chunk_index=c["chunk_index"],
                    similarity_score=c["similarity_score"],
                )
                for c in result["chunks"]
            ],
            retrieval_time_ms=result["retrieval_time_ms"],
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Search failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Search failed"},
        )


@router.post(
    "/kb/{kb_id}/augment",
    response_model=RAGContextResponse,
    summary="Build RAG context for LLM",
)
async def build_rag_context(
    kb_id: uuid.UUID,
    query: str = Query(..., description="Query for context"),
    top_k: int = Query(5, ge=1, le=20),
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Build RAG context string for augmenting LLM prompts."""
    try:
        service = RAGService(db=db, organization_id=org.id, user_id=user.id)
        context = await service.build_rag_context(
            kb_id=kb_id,
            query=query,
            top_k=top_k,
        )

        # Rough token estimate
        tokens_added = len(context) // 4

        return RAGContextResponse(
            status="success",
            context=context,
            source_documents=top_k,
            tokens_added=tokens_added,
        )
    except AgentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": exc.message},
        )
