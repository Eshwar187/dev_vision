"""
Adversarial Authorization & IDOR Integration Tests for DevVision AI Phase 5.

Verifies:
1. Workspace IDOR: Non-member cannot access workspace resources (returns 404).
2. Document IDOR: User from Workspace A cannot access/download documents of Workspace B.
3. Chunk inspection IDOR: User from Workspace A cannot inspect active chunks of Workspace B.
4. Reindex authorization bypass: Member role cannot trigger reindexing (requires admin/owner, 403).
5. RAG query cross-workspace access: Querying another workspace returns 404.
6. Query history cross-workspace access: Query history of another workspace returns 404.
7. Citation excerpt access across tenants: Citations never leak cross-tenant.
8. Anti-enumeration / UUID probing: Non-existent UUIDs yield identical 404 without leaking metadata.
9. Workspace switching race condition: Request for Workspace A with Workspace B token rejected.
10. Unauthorized deletion/mutation: Member role cannot delete workspace documents.
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
    RagQuery,
    RagQueryCitation,
)
from app.modules.rag.mock import MockEmbeddingModel, MockRerankerModel, MockLanguageModel
from app.modules.rag.service import RagService
from app.api.v1.endpoints.rag import get_rag_service
from app.main import app


@pytest.fixture
def mock_rag_service():
    return RagService(
        embedding_model=MockEmbeddingModel(),
        reranker_model=MockRerankerModel(),
        language_model=MockLanguageModel(),
    )


async def create_user_and_workspace(
    db: AsyncSession,
    email_prefix: str,
    role: str = "owner",
):
    """Helper to seed an isolated user, workspace, membership, and auth session."""
    user = User(
        email=f"{email_prefix}_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        display_name=f"User {email_prefix}",
        is_active=True,
    )
    db.add(user)
    await db.flush()

    workspace = Workspace(
        name=f"Workspace {email_prefix}",
        slug=f"ws-{email_prefix}-{uuid.uuid4().hex[:6]}",
        created_by=user.id,
    )
    db.add(workspace)
    await db.flush()

    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=user.id,
        role=role,
    )
    db.add(membership)

    raw_token = f"tok_{email_prefix}_{uuid.uuid4().hex}"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    session = Session(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(session)
    await db.commit()

    cookies = {
        "devvision_session": raw_token,
        "devvision_csrf": f"csrf_{email_prefix}",
    }
    headers = {
        "X-CSRF-Token": f"csrf_{email_prefix}",
    }
    return user, workspace, cookies, headers


@pytest.mark.asyncio
async def test_idor_01_workspace_isolation_non_member_blocked(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """User from Workspace A cannot query or read documents in Workspace B."""
    _, ws_a, cookies_a, headers_a = await create_user_and_workspace(db_session, "tenant_a")
    _, ws_b, _, _ = await create_user_and_workspace(db_session, "tenant_b")

    # Attempt to list documents of workspace B using tenant A session
    res = await async_client.get(
        f"/api/v1/workspaces/{ws_b.id}/documents",
        cookies=cookies_a,
        headers=headers_a,
    )
    assert res.status_code == 404, "Cross-workspace access must return 404 anti-enumeration"


@pytest.mark.asyncio
async def test_idor_02_cross_workspace_document_download_blocked(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """User from Workspace A cannot download document metadata or bytes from Workspace B."""
    _, ws_a, cookies_a, headers_a = await create_user_and_workspace(db_session, "tenant_a")
    _, ws_b, cookies_b, headers_b = await create_user_and_workspace(db_session, "tenant_b")

    # Create document in workspace B
    doc_b = Document(
        workspace_id=ws_b.id,
        original_filename="confidential_b.pdf",
        object_key="workspaces/b/confidential_b.pdf",
        file_size=1024,
        mime_type="application/pdf",
        checksum="hash_b",
        status="ready",
    )
    db_session.add(doc_b)
    await db_session.commit()

    # User A attempts to download document B
    res = await async_client.get(
        f"/api/v1/workspaces/{ws_b.id}/documents/{doc_b.id}/download",
        cookies=cookies_a,
        headers=headers_a,
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_idor_03_chunk_inspection_cross_workspace_blocked(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """User from Workspace A cannot inspect active chunks of Workspace B."""
    _, ws_a, cookies_a, headers_a = await create_user_and_workspace(db_session, "tenant_a")
    _, ws_b, _, _ = await create_user_and_workspace(db_session, "tenant_b")

    doc_b = Document(
        workspace_id=ws_b.id,
        original_filename="secret_architecture.md",
        object_key="workspaces/b/secret.md",
        file_size=512,
        mime_type="text/markdown",
        checksum="hash_secret",
        status="ready",
    )
    db_session.add(doc_b)
    await db_session.commit()

    res = await async_client.get(
        f"/api/v1/workspaces/{ws_b.id}/documents/{doc_b.id}/chunks",
        cookies=cookies_a,
        headers=headers_a,
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_idor_04_reindex_rbac_role_bypass_blocked(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Workspace regular member cannot trigger document reindex; requires admin or owner."""
    user_member, ws, cookies_member, headers_member = await create_user_and_workspace(
        db_session, "member_only", role="member"
    )

    doc = Document(
        workspace_id=ws.id,
        original_filename="spec.txt",
        object_key="workspaces/spec.txt",
        file_size=200,
        mime_type="text/plain",
        checksum="hash_spec",
        status="ready",
    )
    db_session.add(doc)
    await db_session.commit()

    # Member role triggers reindex
    res = await async_client.post(
        f"/api/v1/workspaces/{ws.id}/documents/{doc.id}/reindex",
        cookies=cookies_member,
        headers=headers_member,
    )
    assert res.status_code == 403, "Member role must be forbidden (403) from reindexing"


@pytest.mark.asyncio
async def test_idor_05_rag_query_cross_tenant_blocked(
    async_client: AsyncClient,
    db_session: AsyncSession,
    mock_rag_service,
):
    """User from Workspace A querying Workspace B returns 404."""
    app.dependency_overrides[get_rag_service] = lambda: mock_rag_service
    _, ws_a, cookies_a, headers_a = await create_user_and_workspace(db_session, "tenant_a")
    _, ws_b, _, _ = await create_user_and_workspace(db_session, "tenant_b")

    payload = {"query": "What are the secret API keys?", "top_k": 3}
    res = await async_client.post(
        f"/api/v1/workspaces/{ws_b.id}/rag/query",
        json=payload,
        cookies=cookies_a,
        headers=headers_a,
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_idor_06_rag_history_cross_tenant_blocked(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """User from Workspace A cannot inspect query history of Workspace B."""
    _, ws_a, cookies_a, headers_a = await create_user_and_workspace(db_session, "tenant_a")
    _, ws_b, _, _ = await create_user_and_workspace(db_session, "tenant_b")

    res = await async_client.get(
        f"/api/v1/workspaces/{ws_b.id}/rag/history",
        cookies=cookies_a,
        headers=headers_a,
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_idor_07_citation_snapshot_cross_tenant_leakage_prevented(
    async_client: AsyncClient,
    db_session: AsyncSession,
    mock_rag_service,
):
    """Historical citation snapshots from deleted or other documents do not bleed cross-tenant."""
    app.dependency_overrides[get_rag_service] = lambda: mock_rag_service
    _, ws_a, cookies_a, headers_a = await create_user_and_workspace(db_session, "tenant_a")
    _, ws_b, _, _ = await create_user_and_workspace(db_session, "tenant_b")

    # Insert historical query and citation in workspace B
    q_b = RagQuery(
        workspace_id=ws_b.id,
        user_id=None,
        query_text="Confidential strategy",
        answer="Classified information [1]",
        model_name="qwen2.5-coder:7b-instruct-q4_K_M",
        has_unverified_claims=False,
        retrieval_chunks_count=1,
        processing_time_ms=10,
    )
    db_session.add(q_b)
    await db_session.flush()

    c_b = RagQueryCitation(
        query_id=q_b.id,
        citation_marker="1",
        document_id=None,
        chunk_id=None,
        document_name="b_strategy.pdf",
        page_number=1,
        section_heading="Secret Heading",
        excerpt="Confidential excerpt from Workspace B",
        rank=1,
        score=0.95,
    )
    db_session.add(c_b)
    await db_session.commit()

    # User A requests history from Workspace A
    res_a = await async_client.get(
        f"/api/v1/workspaces/{ws_a.id}/rag/history",
        cookies=cookies_a,
        headers=headers_a,
    )
    assert res_a.status_code == 200
    data = res_a.json()
    assert "b_strategy.pdf" not in str(data)
    assert "Confidential excerpt" not in str(data)


@pytest.mark.asyncio
async def test_idor_08_anti_enumeration_nonexistent_vs_unauthorized(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Opaque 404 returned identically for non-existent workspace vs unauthorized workspace."""
    _, ws_a, cookies_a, headers_a = await create_user_and_workspace(db_session, "tenant_a")
    _, ws_b, _, _ = await create_user_and_workspace(db_session, "tenant_b")
    random_uuid = uuid.uuid4()

    # 1. Accessing existing workspace B where tenant A is not a member
    res_unauth = await async_client.get(
        f"/api/v1/workspaces/{ws_b.id}",
        cookies=cookies_a,
        headers=headers_a,
    )

    # 2. Accessing non-existent workspace UUID
    res_nonexist = await async_client.get(
        f"/api/v1/workspaces/{random_uuid}",
        cookies=cookies_a,
        headers=headers_a,
    )

    assert res_unauth.status_code == 404
    assert res_nonexist.status_code == 404
    # Error structures must be identical to prevent tenant enumeration
    assert res_unauth.json().get("error", {}).get("code") == res_nonexist.json().get("error", {}).get("code")


@pytest.mark.asyncio
async def test_idor_09_workspace_switching_token_mismatch(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Attempting request with CSRF token from another user session is rejected."""
    _, ws_a, cookies_a, headers_a = await create_user_and_workspace(db_session, "tenant_a")
    _, ws_b, cookies_b, headers_b = await create_user_and_workspace(db_session, "tenant_b")

    # Send cookies of user A but CSRF header of user B
    tampered_headers = {"X-CSRF-Token": headers_b["X-CSRF-Token"]}
    res = await async_client.post(
        f"/api/v1/workspaces/{ws_a.id}/documents",
        cookies=cookies_a,
        headers=tampered_headers,
    )
    assert res.status_code in (403, 400), "CSRF mismatch must be rejected"


@pytest.mark.asyncio
async def test_idor_10_unauthorized_document_deletion_blocked(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """User from Workspace A cannot delete document of Workspace B."""
    _, ws_a, cookies_a, headers_a = await create_user_and_workspace(db_session, "tenant_a")
    _, ws_b, _, _ = await create_user_and_workspace(db_session, "tenant_b")

    doc_b = Document(
        workspace_id=ws_b.id,
        original_filename="vital_doc.pdf",
        object_key="workspaces/b/vital.pdf",
        file_size=1024,
        mime_type="application/pdf",
        checksum="hash_vital",
        status="ready",
    )
    db_session.add(doc_b)
    await db_session.commit()

    # Tenant A attempts deletion of doc in workspace B
    res = await async_client.delete(
        f"/api/v1/workspaces/{ws_b.id}/documents/{doc_b.id}",
        cookies=cookies_a,
        headers=headers_a,
    )
    assert res.status_code == 404
    # Ensure document remains untouched
    rem = await db_session.get(Document, doc_b.id)
    assert rem is not None
