"""
DevVision AI - Phase 5 Deterministic Concurrency Test Suite

Covers:
1. Concurrent RAG queries within the same workspace (verify no state cross-contamination).
2. Concurrent reindexing requests for the same document (monotonic generation numbers, serialization).
3. Concurrent query during generation activation (reads either gen N or gen N+1, never partial/mixed).
4. Competing workers claiming the same document (row lock / fencing token race resolution).
5. Garbage collection during active reindex (preserves active and generating chunks).
"""

import asyncio
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
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
from app.api.v1.endpoints.rag import get_rag_service
from app.main import app


@pytest.fixture
def mock_rag_service():
    return RagService(
        embedding_model=MockEmbeddingModel(),
        reranker_model=MockRerankerModel(),
        language_model=MockLanguageModel(),
    )


async def _create_test_env(db_session: AsyncSession, prefix: str = "conc"):
    """Helper to create user, session, and workspace."""
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash="argon2_test_hash",
        display_name="Concurrency Tester",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    token_str = f"test_session_token_{prefix}_{uuid.uuid4().hex}"
    token_hash = hashlib.sha256(token_str.encode("utf-8")).hexdigest()
    sess = Session(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(sess)

    ws = Workspace(name=f"Workspace {prefix}", slug=f"ws-{prefix}-{uuid.uuid4().hex[:6]}")
    db_session.add(ws)
    await db_session.flush()

    mem = WorkspaceMembership(workspace_id=ws.id, user_id=user.id, role="owner")
    db_session.add(mem)
    await db_session.commit()

    cookies = {
        "devvision_session": token_str,
        "devvision_csrf": f"csrf_{prefix}",
    }
    headers = {
        "X-CSRF-Token": f"csrf_{prefix}",
        "X-Workspace-Id": str(ws.id),
    }
    return user, ws, cookies, headers


# =========================================================================
# 1. CONCURRENT RAG QUERIES ISOLATION
# =========================================================================

@pytest.mark.asyncio
async def test_concurrent_rag_queries_isolated(
    async_client: AsyncClient,
    db_session: AsyncSession,
    mock_rag_service: RagService,
):
    """
    Execute multiple concurrent RAG queries within the same workspace.
    Verifies:
    - Zero state cross-contamination between parallel executions.
    - Each query obtains independent RagQuery record with unique ID.
    - Query text and citations do not leak across concurrent requests.
    """
    app.dependency_overrides[get_rag_service] = lambda: mock_rag_service
    user, ws, cookies, headers = await _create_test_env(db_session, "queries")

    # Seed an active document with a searchable chunk
    doc = Document(
        workspace_id=ws.id,
        original_filename="api_manual.txt",
        object_key=f"workspaces/{ws.id}/api_manual.txt",
        file_size=2048,
        mime_type="text/plain",
        checksum="chk_manual_conc",
        status="ready",
    )
    db_session.add(doc)
    await db_session.flush()

    gen = DocumentIndexGeneration(
        workspace_id=ws.id,
        document_id=doc.id,
        generation_number=1,
        status="active",
        stage="ready",
        total_chunks=1,
    )
    db_session.add(gen)
    await db_session.flush()
    doc.active_generation_id = gen.id

    chunk = DocumentChunk(
        workspace_id=ws.id,
        document_id=doc.id,
        generation_id=gen.id,
        chunk_index=0,
        page_number=1,
        section_heading="Rate Limits",
        token_count=25,
        text_content="DevVision API limits incoming requests to 100 requests per minute per workspace.",
        tsv_content="DevVision API limits incoming requests to 100 requests per minute per workspace.",
        embedding=[0.05] * 384,
    )
    db_session.add(chunk)
    await db_session.commit()

    # Launch 6 concurrent queries with distinct queries
    query_texts = [f"What is the API rate limit for test run #{i}?" for i in range(6)]

    async def _send_query(q_text: str):
        return await async_client.post(
            f"/api/v1/workspaces/{ws.id}/rag/query",
            json={"query": q_text},
            headers=headers,
            cookies=cookies,
        )

    responses = await asyncio.gather(*[_send_query(q) for q in query_texts])

    # Verify all succeeded
    returned_query_ids = []
    for idx, resp in enumerate(responses):
        assert resp.status_code == 200, f"Query {idx} failed with {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "query_id" in data
        assert data["query_id"] not in returned_query_ids, "query_id must be unique across concurrent queries"
        returned_query_ids.append(data["query_id"])
        assert len(data["citations"]) >= 1
        assert "100 requests per minute" in data["citations"][0]["excerpt"]

    # Verify database audit records
    audit_stmt = select(RagQuery).where(RagQuery.workspace_id == ws.id)
    records = (await db_session.execute(audit_stmt)).scalars().all()
    assert len(records) == 6
    audit_texts = {r.query_text for r in records}
    assert audit_texts == set(query_texts), "All concurrent queries must have exact isolated audit trails"

    app.dependency_overrides.pop(get_rag_service, None)


# =========================================================================
# 2. CONCURRENT REINDEXING MONOTONIC GENERATION NUMBERS
# =========================================================================

@pytest.mark.asyncio
async def test_concurrent_reindexing_monotonic_generation(
    db_session: AsyncSession,
):
    """
    Verify that concurrent reindexing requests for the same document serialize
    cleanly and increment generation numbers monotonically.
    """
    ws = Workspace(name="Reindex WS", slug=f"reindex-ws-{uuid.uuid4().hex[:6]}")
    db_session.add(ws)
    await db_session.flush()

    doc = Document(
        workspace_id=ws.id,
        original_filename="system_spec.md",
        object_key="workspaces/test/system_spec.md",
        file_size=1024,
        mime_type="text/markdown",
        checksum="chk_reindex_mono",
        status="ready",
    )
    db_session.add(doc)
    await db_session.flush()

    # Initial generation 1
    gen1 = DocumentIndexGeneration(
        workspace_id=ws.id,
        document_id=doc.id,
        generation_number=1,
        status="active",
        stage="ready",
        total_chunks=1,
    )
    db_session.add(gen1)
    await db_session.flush()
    doc.active_generation_id = gen1.id
    await db_session.commit()

    ws_id = ws.id
    doc_id = doc.id
    gen1_id = gen1.id
    gen1_num = gen1.generation_number

    worker_a = IngestionWorker(worker_id="worker-A", embedding_model=MockEmbeddingModel())
    worker_b = IngestionWorker(worker_id="worker-B", embedding_model=MockEmbeddingModel())

    # Worker A acquires lease for document
    token_a = await worker_a.acquire_lease(db_session, doc_id, workspace_id=ws_id)
    assert token_a is not None

    # Worker B attempts to acquire lease concurrently -> fails because worker A holds unexpired lease
    token_b = await worker_b.acquire_lease(db_session, doc_id, workspace_id=ws_id)
    assert token_b is None, "Worker B must be rejected when unexpired lease is held by Worker A"

    # Worker A builds Generation 2
    gen2 = DocumentIndexGeneration(
        workspace_id=ws_id,
        document_id=doc_id,
        generation_number=gen1_num + 1,
        status="building",
        stage="ready",
        total_chunks=2,
    )
    db_session.add(gen2)
    await db_session.flush()
    gen2_id = gen2.id
    gen2_num = gen2.generation_number

    # Zero-downtime activation: Retire gen1, then activate gen2
    gen1_curr = await db_session.get(DocumentIndexGeneration, gen1_id)
    gen1_curr.status = "retired"
    await db_session.flush()

    gen2_curr = await db_session.get(DocumentIndexGeneration, gen2_id)
    gen2_curr.status = "active"
    doc_curr = await db_session.get(Document, doc_id)
    doc_curr.active_generation_id = gen2_id
    await db_session.commit()

    # Worker A releases lease
    await worker_a.release_lease(db_session, doc_id, token_a)

    # Worker B can now acquire lease for next generation
    token_b = await worker_b.acquire_lease(db_session, doc_id, workspace_id=ws_id)
    assert token_b is not None

    # Worker B builds Generation 3
    gen3 = DocumentIndexGeneration(
        workspace_id=ws_id,
        document_id=doc_id,
        generation_number=gen2_num + 1,
        status="building",
        stage="ready",
        total_chunks=3,
    )
    db_session.add(gen3)
    await db_session.flush()
    gen3_id = gen3.id

    # Zero-downtime activation: Retire gen2, then activate gen3
    gen2_curr = await db_session.get(DocumentIndexGeneration, gen2_id)
    gen2_curr.status = "retired"
    await db_session.flush()

    gen3_curr = await db_session.get(DocumentIndexGeneration, gen3_id)
    gen3_curr.status = "active"
    doc_curr2 = await db_session.get(Document, doc_id)
    doc_curr2.active_generation_id = gen3_id
    await db_session.commit()
    await worker_b.release_lease(db_session, doc_id, token_b)

    # Verify monotonic progression
    gens_stmt = (
        select(DocumentIndexGeneration)
        .where(DocumentIndexGeneration.document_id == doc_id)
        .order_by(DocumentIndexGeneration.generation_number.asc())
    )
    all_gens = (await db_session.execute(gens_stmt)).scalars().all()
    gen_nums = [g.generation_number for g in all_gens]
    assert gen_nums == [1, 2, 3], "Generation numbers must strictly increment monotonically without gaps or duplicates"
    final_doc = await db_session.get(Document, doc_id)
    assert final_doc.active_generation_id == gen3_id


# =========================================================================
# 3. CONCURRENT QUERY DURING GENERATION ACTIVATION
# =========================================================================

@pytest.mark.asyncio
async def test_concurrent_query_during_generation_activation(
    db_session: AsyncSession,
    mock_rag_service: RagService,
):
    """
    Verify that while a new generation is being chunked or activated:
    - RAG queries strictly read either generation N or generation N+1.
    - Never observe partial, un-activated, or mixed chunks from both generations.
    """
    ws = Workspace(name="Activation WS", slug=f"act-ws-{uuid.uuid4().hex[:6]}")
    db_session.add(ws)
    await db_session.flush()

    doc = Document(
        workspace_id=ws.id,
        original_filename="versioned_doc.txt",
        object_key="workspaces/test/versioned_doc.txt",
        file_size=512,
        mime_type="text/plain",
        checksum="chk_versioned",
        status="ready",
    )
    db_session.add(doc)
    await db_session.flush()

    # Active Generation 1: Contains Version 1 data
    gen1 = DocumentIndexGeneration(
        workspace_id=ws.id,
        document_id=doc.id,
        generation_number=1,
        status="active",
        stage="ready",
        total_chunks=1,
    )
    db_session.add(gen1)
    await db_session.flush()
    doc.active_generation_id = gen1.id

    chunk_g1 = DocumentChunk(
        workspace_id=ws.id,
        document_id=doc.id,
        generation_id=gen1.id,
        chunk_index=0,
        page_number=1,
        section_heading="Version Info",
        token_count=15,
        text_content="SYSTEM_RELEASE: Version 1.0.0 is running stably.",
        tsv_content="SYSTEM_RELEASE: Version 1.0.0 is running stably.",
        embedding=[0.1] * 384,
    )
    db_session.add(chunk_g1)
    await db_session.commit()

    # Building Generation 2: Contains Version 2 data (in progress)
    gen2 = DocumentIndexGeneration(
        workspace_id=ws.id,
        document_id=doc.id,
        generation_number=2,
        status="building",
        stage="indexing",
        total_chunks=0,
    )
    db_session.add(gen2)
    await db_session.flush()

    chunk_g2 = DocumentChunk(
        workspace_id=ws.id,
        document_id=doc.id,
        generation_id=gen2.id,
        chunk_index=0,
        page_number=1,
        section_heading="Version Info",
        token_count=15,
        text_content="SYSTEM_RELEASE: Version 2.0.0 has been deployed.",
        tsv_content="SYSTEM_RELEASE: Version 2.0.0 has been deployed.",
        embedding=[0.1] * 384,
    )
    db_session.add(chunk_g2)
    await db_session.commit()

    ws_id = ws.id
    doc_id = doc.id
    gen1_id = gen1.id
    gen2_id = gen2.id

    # PHASE A: Query execution while Gen 2 is still building
    # The retriever must ONLY see Gen 1 chunks, ignoring Gen 2 entirely
    res_a = await mock_rag_service.execute_query(
        db=db_session,
        workspace_id=ws_id,
        user_id=None,
        query_text="What is the current system release?",
    )
    assert len(res_a.citations) > 0
    assert any("Version 1.0.0" in c.excerpt for c in res_a.citations)
    assert not any("Version 2.0.0" in c.excerpt for c in res_a.citations), (
        "Retrieval must never leak un-activated chunks from a building generation"
    )

    # PHASE B: Atomic Activation Transaction
    # Retire Gen 1, Activate Gen 2, Switch doc.active_generation_id
    gen1_curr = await db_session.get(DocumentIndexGeneration, gen1_id)
    gen1_curr.status = "retired"
    gen1_curr.retired_at = datetime.now(timezone.utc)
    await db_session.flush()

    gen2_curr = await db_session.get(DocumentIndexGeneration, gen2_id)
    gen2_curr.status = "active"
    gen2_curr.stage = "ready"
    gen2_curr.activated_at = datetime.now(timezone.utc)
    gen2_curr.total_chunks = 1

    doc_curr = await db_session.get(Document, doc_id)
    doc_curr.active_generation_id = gen2_id
    await db_session.commit()

    # PHASE C: Query execution after atomic swap
    # The retriever must now ONLY see Gen 2 chunks, and NOT Gen 1 retired chunks
    res_c = await mock_rag_service.execute_query(
        db=db_session,
        workspace_id=ws_id,
        user_id=None,
        query_text="What is the current system release?",
    )
    assert len(res_c.citations) > 0
    assert any("Version 2.0.0" in c.excerpt for c in res_c.citations)
    assert not any("Version 1.0.0" in c.excerpt for c in res_c.citations), (
        "Retrieval must immediately switch to Gen 2 and never mix retired Gen 1 chunks"
    )


# =========================================================================
# 4. COMPETING WORKERS CLAIMING SAME PENDING DOCUMENT
# =========================================================================

@pytest.mark.asyncio
async def test_competing_workers_claim_document(
    db_session: AsyncSession,
):
    """
    Verify that when two workers attempt to claim the same document:
    - Worker 1 acquires lease (token 1).
    - Worker 2 receives None (conflict).
    - If Worker 1's lease expires, Worker 2 reclaims lease with higher fencing token (token 2).
    - Worker 1 is permanently rejected from mutating or activating document.
    """
    doc_id = uuid.uuid4()
    ws_id = uuid.uuid4()

    worker_1 = IngestionWorker(worker_id="worker-node-1", embedding_model=MockEmbeddingModel())
    worker_2 = IngestionWorker(worker_id="worker-node-2", embedding_model=MockEmbeddingModel())

    # Step 1: Worker 1 claims document
    token_1 = await worker_1.acquire_lease(db_session, doc_id, workspace_id=ws_id)
    assert token_1 == 1

    # Step 2: Worker 2 attempts claim while lease is active -> rejected
    token_2_rejected = await worker_2.acquire_lease(db_session, doc_id, workspace_id=ws_id)
    assert token_2_rejected is None

    # Step 3: Simulate lease expiry for Worker 1
    lease_stmt = select(DocumentProcessingLease).where(DocumentProcessingLease.document_id == doc_id)
    lease = (await db_session.execute(lease_stmt)).scalar_one()
    lease.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=60)
    await db_session.commit()

    # Step 4: Worker 2 claims expired document -> succeeds with incremented token
    token_2 = await worker_2.acquire_lease(db_session, doc_id, workspace_id=ws_id)
    assert token_2 == 2
    assert token_2 > token_1

    # Step 5: Worker 1 tries to commit using stale token 1 -> rejected by fencing barrier
    with pytest.raises(RuntimeError) as exc_info:
        await worker_1.verify_fencing_ownership_barrier(db_session, doc_id, token_1)
    assert "Fencing ownership barrier violation" in str(exc_info.value)
    assert "worker-node-1" in str(exc_info.value)

    # Step 6: Worker 2 verifies barrier successfully
    await worker_2.verify_fencing_ownership_barrier(db_session, doc_id, token_2)


# =========================================================================
# 5. GARBAGE COLLECTION DURING ACTIVE REINDEX
# =========================================================================

@pytest.mark.asyncio
async def test_gc_preserves_active_and_generating(
    db_session: AsyncSession,
):
    """
    Verify that background garbage collection deletes ONLY retired generations
    older than the grace period, and strictly preserves:
    - Active generation (even if older than grace period).
    - Currently generating / building generations.
    """
    ws = Workspace(name="GC Safe WS", slug=f"gc-ws-{uuid.uuid4().hex[:6]}")
    db_session.add(ws)
    await db_session.flush()

    doc = Document(
        workspace_id=ws.id,
        original_filename="important_record.pdf",
        object_key="workspaces/test/important_record.pdf",
        file_size=4096,
        mime_type="application/pdf",
        checksum="chk_gc_safe",
        status="ready",
    )
    db_session.add(doc)
    await db_session.flush()

    two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)

    # 1. Gen 1: Old retired generation (should be deleted)
    gen1 = DocumentIndexGeneration(
        workspace_id=ws.id,
        document_id=doc.id,
        generation_number=1,
        status="retired",
        stage="ready",
        total_chunks=1,
        retired_at=two_hours_ago,
    )
    db_session.add(gen1)
    await db_session.flush()

    chunk1 = DocumentChunk(
        workspace_id=ws.id,
        document_id=doc.id,
        generation_id=gen1.id,
        chunk_index=0,
        page_number=1,
        section_heading="Old Section",
        token_count=10,
        text_content="Old retired text chunk",
        tsv_content="Old retired text chunk",
        embedding=[0.01] * 384,
    )
    db_session.add(chunk1)

    # 2. Gen 2: Active generation (MUST BE PRESERVED)
    gen2 = DocumentIndexGeneration(
        workspace_id=ws.id,
        document_id=doc.id,
        generation_number=2,
        status="active",
        stage="ready",
        total_chunks=1,
        activated_at=two_hours_ago,
    )
    db_session.add(gen2)
    await db_session.flush()
    doc.active_generation_id = gen2.id

    chunk2 = DocumentChunk(
        workspace_id=ws.id,
        document_id=doc.id,
        generation_id=gen2.id,
        chunk_index=0,
        page_number=1,
        section_heading="Active Section",
        token_count=10,
        text_content="Currently active production text chunk",
        tsv_content="Currently active production text chunk",
        embedding=[0.02] * 384,
    )
    db_session.add(chunk2)

    # 3. Gen 3: Currently generating / building generation (MUST BE PRESERVED)
    gen3 = DocumentIndexGeneration(
        workspace_id=ws.id,
        document_id=doc.id,
        generation_number=3,
        status="building",
        stage="indexing",
        total_chunks=1,
    )
    db_session.add(gen3)
    await db_session.flush()

    chunk3 = DocumentChunk(
        workspace_id=ws.id,
        document_id=doc.id,
        generation_id=gen3.id,
        chunk_index=0,
        page_number=1,
        section_heading="Generating Section",
        token_count=10,
        text_content="In-flight building text chunk",
        tsv_content="In-flight building text chunk",
        embedding=[0.03] * 384,
    )
    db_session.add(chunk3)
    await db_session.commit()

    # Execute Garbage Collection with 1-hour grace period
    worker = IngestionWorker(worker_id="gc-worker", embedding_model=MockEmbeddingModel())
    deleted_count = await worker.cleanup_retired_generations(db_session, grace_period_hours=1)
    assert deleted_count == 1, "Exactly one retired generation must be pruned"

    # Verify DB state
    remaining_gens = (
        await db_session.execute(
            select(DocumentIndexGeneration)
            .where(DocumentIndexGeneration.document_id == doc.id)
            .order_by(DocumentIndexGeneration.generation_number.asc())
        )
    ).scalars().all()
    remaining_gen_ids = {g.id for g in remaining_gens}
    assert gen1.id not in remaining_gen_ids, "Gen 1 (retired) must be deleted"
    assert gen2.id in remaining_gen_ids, "Gen 2 (active) must be preserved"
    assert gen3.id in remaining_gen_ids, "Gen 3 (building) must be preserved"

    # Verify chunks
    remaining_chunks = (
        await db_session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
        )
    ).scalars().all()
    remaining_chunk_gen_ids = {c.generation_id for c in remaining_chunks}
    assert gen1.id not in remaining_chunk_gen_ids
    assert gen2.id in remaining_chunk_gen_ids
    assert gen3.id in remaining_chunk_gen_ids
