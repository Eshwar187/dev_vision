import io
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.security import generate_session_token, generate_csrf_token, hash_session_token
from app.core.storage import get_storage
from app.modules.identity.models import Session, User
from app.modules.workspaces.models import Workspace, WorkspaceMembership

settings = get_settings()


class DummyStreamingBody:
    """Mock streaming body for in-memory unit/integration tests."""

    def __init__(self, data: bytes):
        self.data = data

    def iter_chunks(self, chunk_size: int = 64 * 1024):
        bio = io.BytesIO(self.data)
        while True:
            chunk = bio.read(chunk_size)
            if not chunk:
                break
            yield chunk


@pytest_asyncio.fixture
async def setup_test_users_and_workspaces(db_session: AsyncSession):
    """Creates two users, two workspaces, and establishes session cookies for each."""
    # User A (Workspace A Owner)
    user_a = User(
        id=uuid.uuid4(),
        email="alice@example.com",
        password_hash="argon2id_hash_placeholder",
        display_name="Alice A",
        is_active=True,
    )
    # User B (Workspace B Owner)
    user_b = User(
        id=uuid.uuid4(),
        email="bob@example.com",
        password_hash="argon2id_hash_placeholder",
        display_name="Bob B",
        is_active=True,
    )
    # User C (Workspace A Member)
    user_c = User(
        id=uuid.uuid4(),
        email="charlie@example.com",
        password_hash="argon2id_hash_placeholder",
        display_name="Charlie C",
        is_active=True,
    )
    db_session.add_all([user_a, user_b, user_c])
    await db_session.flush()

    # Workspace A
    ws_a = Workspace(id=uuid.uuid4(), name="Workspace A", slug="workspace-a", created_by=user_a.id)
    # Workspace B
    ws_b = Workspace(id=uuid.uuid4(), name="Workspace B", slug="workspace-b", created_by=user_b.id)
    db_session.add_all([ws_a, ws_b])
    await db_session.flush()

    # Memberships
    m_a_owner = WorkspaceMembership(id=uuid.uuid4(), user_id=user_a.id, workspace_id=ws_a.id, role="owner")
    m_b_owner = WorkspaceMembership(id=uuid.uuid4(), user_id=user_b.id, workspace_id=ws_b.id, role="owner")
    m_a_member = WorkspaceMembership(id=uuid.uuid4(), user_id=user_c.id, workspace_id=ws_a.id, role="member")
    db_session.add_all([m_a_owner, m_b_owner, m_a_member])

    # Sessions
    raw_session_a = generate_session_token()
    raw_session_b = generate_session_token()
    raw_session_c = generate_session_token()

    from datetime import datetime, timedelta, timezone
    exp = datetime.now(timezone.utc) + timedelta(days=7)

    s_a = Session(id=uuid.uuid4(), user_id=user_a.id, token_hash=hash_session_token(raw_session_a), expires_at=exp)
    s_b = Session(id=uuid.uuid4(), user_id=user_b.id, token_hash=hash_session_token(raw_session_b), expires_at=exp)
    s_c = Session(id=uuid.uuid4(), user_id=user_c.id, token_hash=hash_session_token(raw_session_c), expires_at=exp)
    db_session.add_all([s_a, s_b, s_c])

    await db_session.commit()

    csrf_a = generate_csrf_token()
    csrf_b = generate_csrf_token()
    csrf_c = generate_csrf_token()

    return {
        "user_a": user_a,
        "user_b": user_b,
        "user_c": user_c,
        "ws_a": ws_a,
        "ws_b": ws_b,
        "session_a": raw_session_a,
        "session_b": raw_session_b,
        "session_c": raw_session_c,
        "csrf_a": csrf_a,
        "csrf_b": csrf_b,
        "csrf_c": csrf_c,
    }


@pytest.mark.asyncio
async def test_upload_document_success(async_client: AsyncClient, setup_test_users_and_workspaces, monkeypatch):
    data = setup_test_users_and_workspaces
    ws_id = data["ws_a"].id
    cookies = {
        settings.SESSION_COOKIE_NAME: data["session_a"],
        settings.CSRF_COOKIE_NAME: data["csrf_a"],
    }
    headers = {"X-CSRF-Token": data["csrf_a"]}

    # Mock storage
    uploaded_keys = {}
    storage = get_storage()
    monkeypatch.setattr(storage, "upload_bytes", lambda key, data, content_type: uploaded_keys.update({key: data}))

    file_content = b"%PDF-1.7\nSample Architecture Specification PDF"
    files = {"file": ("architecture.v1.pdf", file_content, "application/pdf")}

    res = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        cookies=cookies,
        headers=headers,
        files=files,
    )
    assert res.status_code == 201
    body = res.json()
    assert body["original_filename"] == "architecture.v1.pdf"
    assert body["mime_type"] == "application/pdf"
    assert body["file_size"] == len(file_content)
    assert body["status"] == "uploaded"
    assert len(uploaded_keys) == 1


@pytest.mark.asyncio
async def test_upload_duplicate_document_rejection(async_client: AsyncClient, setup_test_users_and_workspaces, monkeypatch):
    data = setup_test_users_and_workspaces
    ws_id = data["ws_a"].id
    cookies = {
        settings.SESSION_COOKIE_NAME: data["session_a"],
        settings.CSRF_COOKIE_NAME: data["csrf_a"],
    }
    headers = {"X-CSRF-Token": data["csrf_a"]}

    storage = get_storage()
    monkeypatch.setattr(storage, "upload_bytes", lambda key, data, content_type: None)

    file_content = b"%PDF-1.4\nDuplicate Document Test Content"
    files1 = {"file": ("first_upload.pdf", file_content, "application/pdf")}

    # 1. First upload succeeds
    res1 = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        cookies=cookies,
        headers=headers,
        files=files1,
    )
    assert res1.status_code == 201

    # 2. Identical upload in the SAME workspace fails with 409 Conflict
    files2 = {"file": ("second_upload_different_name.pdf", file_content, "application/pdf")}
    res2 = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        cookies=cookies,
        headers=headers,
        files=files2,
    )
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "DUPLICATE_DOCUMENT"


@pytest.mark.asyncio
async def test_duplicate_document_allowed_across_different_workspaces(async_client: AsyncClient, setup_test_users_and_workspaces, monkeypatch):
    data = setup_test_users_and_workspaces
    cookies_a = {
        settings.SESSION_COOKIE_NAME: data["session_a"],
        settings.CSRF_COOKIE_NAME: data["csrf_a"],
    }
    cookies_b = {
        settings.SESSION_COOKIE_NAME: data["session_b"],
        settings.CSRF_COOKIE_NAME: data["csrf_b"],
    }
    storage = get_storage()
    monkeypatch.setattr(storage, "upload_bytes", lambda key, data, content_type: None)

    file_content = b"%PDF-1.4\nCross Workspace Allowed File Content"

    # Upload to Workspace A
    res_a = await async_client.post(
        f"/api/v1/workspaces/{data['ws_a'].id}/documents",
        cookies=cookies_a,
        headers={"X-CSRF-Token": data["csrf_a"]},
        files={"file": ("doc.pdf", file_content, "application/pdf")},
    )
    assert res_a.status_code == 201

    # Upload identical file to Workspace B succeeds (tenant isolation)
    res_b = await async_client.post(
        f"/api/v1/workspaces/{data['ws_b'].id}/documents",
        cookies=cookies_b,
        headers={"X-CSRF-Token": data["csrf_b"]},
        files={"file": ("doc.pdf", file_content, "application/pdf")},
    )
    assert res_b.status_code == 201


@pytest.mark.asyncio
async def test_workspace_isolation_idor_defense(async_client: AsyncClient, setup_test_users_and_workspaces, monkeypatch):
    """User B attempts to access User A's Workspace A document -> must return 404."""
    data = setup_test_users_and_workspaces
    cookies_a = {
        settings.SESSION_COOKIE_NAME: data["session_a"],
        settings.CSRF_COOKIE_NAME: data["csrf_a"],
    }
    cookies_b = {
        settings.SESSION_COOKIE_NAME: data["session_b"],
        settings.CSRF_COOKIE_NAME: data["csrf_b"],
    }
    storage = get_storage()
    monkeypatch.setattr(storage, "upload_bytes", lambda key, data, content_type: None)

    # User A uploads doc
    res_upload = await async_client.post(
        f"/api/v1/workspaces/{data['ws_a'].id}/documents",
        cookies=cookies_a,
        headers={"X-CSRF-Token": data["csrf_a"]},
        files={"file": ("secret.pdf", b"%PDF-1.4\nConfidential Data", "application/pdf")},
    )
    assert res_upload.status_code == 201
    doc_id = res_upload.json()["id"]

    # User B tries to view metadata in Workspace A -> 404 (non-member)
    res_meta = await async_client.get(
        f"/api/v1/workspaces/{data['ws_a'].id}/documents/{doc_id}",
        cookies=cookies_b,
    )
    assert res_meta.status_code == 404

    # User B tries to download from Workspace A -> 404
    res_dl = await async_client.get(
        f"/api/v1/workspaces/{data['ws_a'].id}/documents/{doc_id}/download",
        cookies=cookies_b,
    )
    assert res_dl.status_code == 404

    # User B tries to delete from Workspace A -> 404
    res_del = await async_client.delete(
        f"/api/v1/workspaces/{data['ws_a'].id}/documents/{doc_id}",
        cookies=cookies_b,
        headers={"X-CSRF-Token": data["csrf_b"]},
    )
    assert res_del.status_code == 404


@pytest.mark.asyncio
async def test_rbac_deletion_rules(async_client: AsyncClient, setup_test_users_and_workspaces, monkeypatch):
    data = setup_test_users_and_workspaces
    cookies_a = {
        settings.SESSION_COOKIE_NAME: data["session_a"],
        settings.CSRF_COOKIE_NAME: data["csrf_a"],
    }
    cookies_c = {
        settings.SESSION_COOKIE_NAME: data["session_c"],
        settings.CSRF_COOKIE_NAME: data["csrf_c"],
    }
    storage = get_storage()
    monkeypatch.setattr(storage, "upload_bytes", lambda key, data, content_type: None)
    monkeypatch.setattr(storage, "delete_object", lambda key: True)

    # 1. Owner (Alice) uploads Doc 1
    res1 = await async_client.post(
        f"/api/v1/workspaces/{data['ws_a'].id}/documents",
        cookies=cookies_a,
        headers={"X-CSRF-Token": data["csrf_a"]},
        files={"file": ("alice_doc.pdf", b"%PDF-1.4\nAlice doc", "application/pdf")},
    )
    doc1_id = res1.json()["id"]

    # 2. Member (Charlie) uploads Doc 2
    res2 = await async_client.post(
        f"/api/v1/workspaces/{data['ws_a'].id}/documents",
        cookies=cookies_c,
        headers={"X-CSRF-Token": data["csrf_c"]},
        files={"file": ("charlie_doc.pdf", b"%PDF-1.4\nCharlie doc", "application/pdf")},
    )
    doc2_id = res2.json()["id"]

    # 3. Member (Charlie) tries to delete Owner's doc -> 403 Forbidden
    res_fail = await async_client.delete(
        f"/api/v1/workspaces/{data['ws_a'].id}/documents/{doc1_id}",
        cookies=cookies_c,
        headers={"X-CSRF-Token": data["csrf_c"]},
    )
    assert res_fail.status_code == 403

    # 4. Member (Charlie) deletes own doc -> 200 OK
    res_member_del = await async_client.delete(
        f"/api/v1/workspaces/{data['ws_a'].id}/documents/{doc2_id}",
        cookies=cookies_c,
        headers={"X-CSRF-Token": data["csrf_c"]},
    )
    assert res_member_del.status_code == 200

    # 5. Owner (Alice) deletes remaining doc -> 200 OK
    res_owner_del = await async_client.delete(
        f"/api/v1/workspaces/{data['ws_a'].id}/documents/{doc1_id}",
        cookies=cookies_a,
        headers={"X-CSRF-Token": data["csrf_a"]},
    )
    assert res_owner_del.status_code == 200


@pytest.mark.asyncio
async def test_download_streaming(async_client: AsyncClient, setup_test_users_and_workspaces, monkeypatch):
    data = setup_test_users_and_workspaces
    ws_id = data["ws_a"].id
    cookies = {
        settings.SESSION_COOKIE_NAME: data["session_a"],
        settings.CSRF_COOKIE_NAME: data["csrf_a"],
    }
    file_bytes = b"%PDF-1.4\nExact download payload test"

    storage = get_storage()
    monkeypatch.setattr(storage, "upload_bytes", lambda key, data, content_type: None)
    monkeypatch.setattr(storage, "get_object_stream", lambda key: DummyStreamingBody(file_bytes))

    # Upload
    res_up = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        cookies=cookies,
        headers={"X-CSRF-Token": data["csrf_a"]},
        files={"file": ("report.pdf", file_bytes, "application/pdf")},
    )
    doc_id = res_up.json()["id"]

    # Download
    res_dl = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/documents/{doc_id}/download",
        cookies=cookies,
    )
    assert res_dl.status_code == 200
    assert res_dl.content == file_bytes
    assert "attachment" in res_dl.headers["Content-Disposition"]
    assert res_dl.headers["Content-Type"] == "application/pdf"
    assert res_dl.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.asyncio
async def test_cursor_pagination(async_client: AsyncClient, setup_test_users_and_workspaces, monkeypatch):
    data = setup_test_users_and_workspaces
    ws_id = data["ws_a"].id
    cookies = {
        settings.SESSION_COOKIE_NAME: data["session_a"],
        settings.CSRF_COOKIE_NAME: data["csrf_a"],
    }
    storage = get_storage()
    monkeypatch.setattr(storage, "upload_bytes", lambda key, data, content_type: None)

    # Upload 3 documents
    for i in range(3):
        content = f"%PDF-1.4\nDoc number {i}".encode("utf-8")
        await async_client.post(
            f"/api/v1/workspaces/{ws_id}/documents",
            cookies=cookies,
            headers={"X-CSRF-Token": data["csrf_a"]},
            files={"file": (f"doc_{i}.pdf", content, "application/pdf")},
        )

    # Page 1: limit=2
    res_p1 = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/documents?limit=2",
        cookies=cookies,
    )
    assert res_p1.status_code == 200
    p1 = res_p1.json()
    assert len(p1["items"]) == 2
    assert p1["next_cursor"] is not None

    # Page 2: with cursor
    res_p2 = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/documents?limit=2&cursor={p1['next_cursor']}",
        cookies=cookies,
    )
    assert res_p2.status_code == 200
    p2 = res_p2.json()
    assert len(p2["items"]) == 1
    assert p2["next_cursor"] is None
