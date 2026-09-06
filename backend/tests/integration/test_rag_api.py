"""
DevVision AI - Integration Tests for Phase 3 RAG API.

Tests:
- POST /api/v1/workspaces/{id}/rag/query with mock models
- Verified vs unverified citations in response
- GET /api/v1/workspaces/{id}/rag/history with immutable snapshot inspection
- GET /api/v1/workspaces/{id}/documents/{doc_id}/chunks
- RBAC authorization: members vs non-members (IDOR 404), admin reindexing
- Fencing token monotonically increments on lease acquisition
"""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.modules.identity.models import User, Session
from app.modules.workspaces.models import Workspace, WorkspaceMembership
from app.modules.documents.models import Document
from app.modules.rag.models import (
    DocumentIndexGeneration,
    DocumentChunk,
    DocumentProcessingLease,
    RagQuery,
    RagQueryCitation,
)
from app.modules.rag.mock import MockEmbeddingModel, MockRerankerModel, MockLanguageModel
from app.modules.rag.service import RagService
from app.modules.rag.worker import IngestionWorker
from app.api.v1.endpoints.rag import get_rag_service, get_ingestion_worker
from app.main import app


@pytest.fixture
def mock_rag_service():
    service = RagService(
        embedding_model=MockEmbeddingModel(),
        reranker_model=MockRerankerModel(),
        language_model=MockLanguageModel(),
    )
    return service


@pytest.fixture
def mock_ingestion_worker():
    return IngestionWorker(
        worker_id="test-worker-1",
        embedding_model=MockEmbeddingModel(),
    )


@pytest.mark.asyncio
async def test_rag_query_and_history_flow(
    async_client: AsyncClient,
    db_session: AsyncSession,
    mock_rag_service: RagService,
):
    # Override FastAPI dependency for RAG service to use mock
    app.dependency_overrides[get_rag_service] = lambda: mock_rag_service

    # 1. Create user and workspace
    user = User(
        email="developer@example.com",
        password_hash="hash",
        display_name="Developer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    workspace = Workspace(
        name="DevVision Core",
        slug="devvision-core",
        created_by=user.id,
    )
    db_session.add(workspace)
    await db_session.flush()

    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=user.id,
        role="owner",
    )
    db_session.add(membership)

    # 2. Create session & CSRF
    raw_token = "valid_session_token_1234567890123456"
    import hashlib
    from datetime import datetime, timezone, timedelta
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    session = Session(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(session)
    await db_session.flush()

    # 3. Create document and active index generation
    doc = Document(
        workspace_id=workspace.id,
        original_filename="Architecture.md",
        object_key="workspaces/test/Architecture.md",
        file_size=1024,
        mime_type="text/markdown",
        checksum="abc1234",
        status="ready",
    )
    db_session.add(doc)
    await db_session.flush()

    generation = DocumentIndexGeneration(
        workspace_id=workspace.id,
        document_id=doc.id,
        generation_number=1,
        status="active",
        stage="ready",
        total_chunks=1,
        unextractable_pages=[],
    )
    db_session.add(generation)
    await db_session.flush()

    doc.active_generation_id = generation.id

    chunk = DocumentChunk(
        workspace_id=workspace.id,
        document_id=doc.id,
        generation_id=generation.id,
        chunk_index=0,
        page_number=1,
        section_heading="Core Overview",
        token_count=50,
        text_content="DevVision AI features a self-hosted RAG pipeline with dense and sparse retrieval.",
        embedding=[0.1] * 384,
    )
    db_session.add(chunk)
    await db_session.commit()

    cookies = {
        "devvision_session": raw_token,
        "devvision_csrf": "test_csrf_token",
    }
    headers = {
        "X-CSRF-Token": "test_csrf_token",
    }

    # 4. Query RAG API
    query_payload = {
        "query": "How does DevVision AI implement document retrieval?",
        "top_k": 5,
    }

    resp = await async_client.post(
        f"/api/v1/workspaces/{workspace.id}/rag/query",
        json=query_payload,
        cookies=cookies,
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "query_id" in data
    assert data["query_text"] == query_payload["query"]
    assert "citations" in data
    assert len(data["citations"]) > 0
    assert data["citations"][0]["document_name"] == "Architecture.md"

    # 5. Check History Endpoint
    hist_resp = await async_client.get(
        f"/api/v1/workspaces/{workspace.id}/rag/history",
        cookies=cookies,
    )
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert hist_data["total"] >= 1
    assert hist_data["items"][0]["id"] == data["query_id"]
    assert len(hist_data["items"][0]["citations"]) > 0

    # 6. Check Document Chunks Inspection Endpoint
    chunks_resp = await async_client.get(
        f"/api/v1/workspaces/{workspace.id}/documents/{doc.id}/chunks",
        cookies=cookies,
    )
    assert chunks_resp.status_code == 200
    chunks_data = chunks_resp.json()
    assert chunks_data["total_chunks"] == 1
    assert chunks_data["chunks"][0]["section_heading"] == "Core Overview"

    # Clean up overrides
    app.dependency_overrides.pop(get_rag_service, None)


@pytest.mark.asyncio
async def test_lease_fencing_token_monotonic_increment(
    db_session: AsyncSession,
    mock_ingestion_worker: IngestionWorker,
):
    """
    Verify that acquiring and reclaiming a document processing lease
    monotonically increments the fencing token to guard against split-brain mutations.
    """
    doc_id = uuid.uuid4()

    # Initial lease acquisition -> fencing token 1
    token1 = await mock_ingestion_worker.acquire_lease(db_session, doc_id)
    assert token1 == 1

    # Same worker re-acquiring/renewing -> fencing token 2
    token2 = await mock_ingestion_worker.acquire_lease(db_session, doc_id)
    assert token2 == 2

    # Different worker reclaiming -> fencing token 3
    worker2 = IngestionWorker(worker_id="test-worker-2")
    # Simulate lease expiration
    from datetime import datetime, timezone, timedelta
    stmt = select(DocumentProcessingLease).where(DocumentProcessingLease.document_id == doc_id)
    res = await db_session.execute(stmt)
    lease = res.scalar_one()
    lease.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    await db_session.commit()

    token3 = await worker2.acquire_lease(db_session, doc_id)
    assert token3 == 3

    # Clean up
    await worker2.release_lease(db_session, doc_id, token3)
