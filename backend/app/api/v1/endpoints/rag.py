"""
DevVision AI - Phase 3 RAG API Endpoints.

Provides:
- POST /workspaces/{workspace_id}/rag/query (Member-accessible workspace RAG query with citations)
- GET /workspaces/{workspace_id}/rag/history (Member-accessible query history with immutable snapshots)
- POST /workspaces/{workspace_id}/documents/{document_id}/reindex (Admin/Owner reindex trigger)
- GET /workspaces/{workspace_id}/documents/{document_id}/chunks (Member inspectable active chunks)
"""

import asyncio
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.dependencies import (
    get_current_active_user,
    require_workspace_member,
    require_workspace_role,
    verify_csrf_token,
)
from app.core.database import get_db
from app.core.exceptions import (
    DocumentNotFoundException,
    EntityNotFoundException,
    ValidationException,
    AuthorizationException,
)
from app.modules.identity.models import User
from app.modules.workspaces.models import WorkspaceMembership
from app.modules.documents.models import Document
from app.modules.rag.schemas import (
    RagQueryRequest,
    RagQueryResponse,
    RagCitationOut,
    RagHistoryResponse,
    RagHistoryItem,
    ReindexResponse,
    DocumentChunksResponse,
    DocumentChunkOut,
)
from app.modules.rag.service import RagService
from app.modules.rag.worker import IngestionWorker

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["RAG"])


# Singleton service instances for production dependency injection
_rag_service_instance: Optional[RagService] = None
_ingestion_worker_instance: Optional[IngestionWorker] = None


def get_rag_service() -> RagService:
    global _rag_service_instance
    if _rag_service_instance is None:
        _rag_service_instance = RagService()
    return _rag_service_instance


def get_ingestion_worker() -> IngestionWorker:
    global _ingestion_worker_instance
    if _ingestion_worker_instance is None:
        _ingestion_worker_instance = IngestionWorker()
    return _ingestion_worker_instance


@router.post(
    "/rag/query",
    response_model=RagQueryResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_csrf_token)],
    summary="Execute RAG query against workspace documents",
)
async def execute_rag_query(
    workspace_id: uuid.UUID,
    payload: RagQueryRequest,
    current_user: User = Depends(get_current_active_user),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
    rag_service: RagService = Depends(get_rag_service),
) -> RagQueryResponse:
    """
    Executes hybrid dense + sparse retrieval and generates an LLM response with citations.
    Enforces sentence-level citation verification with automatic single retry remediation.
    """
    clean_query = payload.query.strip()
    if len(clean_query) < 2:
        raise ValidationException("Query must be at least 2 characters long.")

    result = await rag_service.execute_query(
        db=db,
        workspace_id=workspace_id,
        user_id=current_user.id,
        query_text=clean_query,
        top_k=payload.top_k,
    )

    citations_out = [
        RagCitationOut(
            citation_marker=c.citation_marker,
            document_id=c.document_id,
            chunk_id=c.chunk_id,
            document_name=c.document_name,
            page_number=c.page_number,
            section_heading=c.section_heading,
            excerpt=c.excerpt,
            rank=c.rank,
            score=c.score,
        )
        for c in result.citations
    ]

    return RagQueryResponse(
        query_id=result.id,
        query_text=result.query_text,
        answer=result.answer,
        has_unverified_claims=result.has_unverified_claims,
        processing_time_ms=result.processing_time_ms,
        citations=citations_out,
        created_at=result.created_at,
    )


@router.get(
    "/rag/history",
    response_model=RagHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve workspace query history with immutable citation snapshots",
)
async def get_rag_history(
    workspace_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_active_user),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
    rag_service: RagService = Depends(get_rag_service),
) -> RagHistoryResponse:
    """
    Returns query history with immutable citation snapshots for the workspace.
    Snapshots remain inspectable even after source document or chunk deletion.
    """
    items = await rag_service.get_history(
        db=db,
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
    )

    history_items = []
    for q in items:
        citations = [
            RagCitationOut(
                citation_marker=c.citation_marker,
                document_id=c.document_id,
                chunk_id=c.chunk_id,
                document_name=c.document_name,
                page_number=c.page_number,
                section_heading=c.section_heading,
                excerpt=c.excerpt,
                rank=c.rank,
                score=c.score,
            )
            for c in q.citations
        ]
        history_items.append(
            RagHistoryItem(
                id=q.id,
                workspace_id=q.workspace_id,
                user_id=q.user_id,
                query_text=q.query_text,
                answer=q.answer,
                has_unverified_claims=q.has_unverified_claims,
                retrieval_chunks_count=q.retrieval_chunks_count,
                processing_time_ms=q.processing_time_ms,
                created_at=q.created_at,
                citations=citations,
            )
        )

    return RagHistoryResponse(items=history_items, total=len(history_items))


@router.post(
    "/documents/{document_id}/reindex",
    response_model=ReindexResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_csrf_token)],
    summary="Trigger zero-downtime document reindexing (Admin/Owner only)",
)
async def reindex_document(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    membership: WorkspaceMembership = Depends(require_workspace_role("admin", "owner")),
    db: AsyncSession = Depends(get_db),
    worker: IngestionWorker = Depends(get_ingestion_worker),
) -> ReindexResponse:
    """
    Triggers reindexing for a document in a background worker task.
    Creates a new index generation, indexes chunks, and activates zero-downtime once complete.
    """
    doc = await db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
        )
    )
    if not doc:
        raise DocumentNotFoundException()

    # Launch background indexing task
    background_tasks.add_task(
        worker.index_document,
        document_id=document_id,
        trigger_reason="manual_reindex",
    )

    return ReindexResponse(
        document_id=document_id,
        generation_id=None,
        status="processing",
        message="Document reindexing queued.",
    )


@router.get(
    "/documents/{document_id}/chunks",
    response_model=DocumentChunksResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect indexed chunks for the active generation of a document",
)
async def get_document_chunks(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
    rag_service: RagService = Depends(get_rag_service),
) -> DocumentChunksResponse:
    """
    Returns chunks belonging to the currently active generation of the document.
    """
    doc = await db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
        )
    )
    if not doc:
        raise DocumentNotFoundException()

    chunks = await rag_service.get_document_chunks(db=db, document_id=document_id)
    chunks_out = [
        DocumentChunkOut(
            id=c.id,
            chunk_index=c.chunk_index,
            content=c.content,
            page_number=c.page_number,
            section_heading=c.section_heading,
            token_count=c.token_count,
            generation_id=c.generation_id,
            created_at=c.created_at,
        )
        for c in chunks
    ]

    return DocumentChunksResponse(
        document_id=document_id,
        active_generation_id=doc.active_generation_id,
        total_chunks=len(chunks_out),
        chunks=chunks_out,
    )
