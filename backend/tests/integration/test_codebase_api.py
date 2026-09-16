import io
import uuid
import zipfile
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import generate_csrf_token, generate_session_token, hash_session_token
from app.main import app as fastapi_app
from app.api.v1.endpoints.codebase import get_codebase_service
from app.modules.codebase.retrieval import HybridCodeRetriever
from app.modules.codebase.service import CodebaseService
from app.modules.identity.models import Session, User
from app.modules.rag.mock import MockEmbeddingModel, MockLanguageModel, MockRerankerModel
from app.modules.workspaces.models import Workspace, WorkspaceMembership

settings = get_settings()


@pytest.fixture(autouse=True)
def override_codebase_service():
    mock_retriever = HybridCodeRetriever(
        embedding_model=MockEmbeddingModel(),
        reranker_model=MockRerankerModel(),
    )
    mock_service = CodebaseService(
        retriever=mock_retriever,
        llm_client=MockLanguageModel(
            default_response="The auth service verifies tokens [1]."
        ),
    )
    fastapi_app.dependency_overrides[get_codebase_service] = lambda: mock_service
    yield mock_service
    fastapi_app.dependency_overrides.pop(get_codebase_service, None)


def create_mock_repo_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "src/auth.py",
            (
                "import os\n\n"
                "class AuthService:\n"
                "    def verify_token(self, token: str) -> bool:\n"
                "        return token == 'valid'\n\n"
                "def login(user: str) -> str:\n"
                "    return 'token_123'\n"
            ),
        )
        zf.writestr(
            "src/models.py",
            (
                "class User:\n"
                "    def __init__(self, name: str):\n"
                "        self.name = name\n"
            ),
        )
        zf.writestr("README.md", "# DevVision Codebase\nSample repo.")
    return buf.getvalue()


@pytest_asyncio.fixture
async def setup_codebase_users(db_session: AsyncSession):
    # User 1 (Owner of Workspace 1)
    u1 = User(
        id=uuid.uuid4(),
        email="alice@code.com",
        password_hash="argon2id_placeholder",
        display_name="Alice Dev",
        is_active=True,
    )
    # User 2 (Owner of Workspace 2)
    u2 = User(
        id=uuid.uuid4(),
        email="bob@code.com",
        password_hash="argon2id_placeholder",
        display_name="Bob Dev",
        is_active=True,
    )
    db_session.add_all([u1, u2])
    await db_session.flush()

    from datetime import datetime, timedelta, timezone
    exp = datetime.now(timezone.utc) + timedelta(days=7)

    w1 = Workspace(id=uuid.uuid4(), name="Alice Workspace", slug="alice-ws", created_by=u1.id)
    w2 = Workspace(id=uuid.uuid4(), name="Bob Workspace", slug="bob-ws", created_by=u2.id)
    db_session.add_all([w1, w2])
    await db_session.flush()

    m1 = WorkspaceMembership(id=uuid.uuid4(), workspace_id=w1.id, user_id=u1.id, role="owner")
    m2 = WorkspaceMembership(id=uuid.uuid4(), workspace_id=w2.id, user_id=u2.id, role="owner")
    db_session.add_all([m1, m2])
    await db_session.flush()

    raw_token_1 = generate_session_token()
    raw_token_2 = generate_session_token()
    csrf_1 = generate_csrf_token()
    csrf_2 = generate_csrf_token()

    s1 = Session(
        id=uuid.uuid4(),
        user_id=u1.id,
        token_hash=hash_session_token(raw_token_1),
        expires_at=exp,
        user_agent="pytest",
        ip_address="127.0.0.1",
    )
    s2 = Session(
        id=uuid.uuid4(),
        user_id=u2.id,
        token_hash=hash_session_token(raw_token_2),
        expires_at=exp,
        user_agent="pytest",
        ip_address="127.0.0.1",
    )
    db_session.add_all([s1, s2])
    await db_session.commit()

    return {
        "w1": w1,
        "w2": w2,
        "u1": u1,
        "u2": u2,
        "cookies_1": {
            settings.SESSION_COOKIE_NAME: raw_token_1,
            settings.CSRF_COOKIE_NAME: csrf_1,
        },
        "headers_1": {"X-CSRF-Token": csrf_1},
        "cookies_2": {
            settings.SESSION_COOKIE_NAME: raw_token_2,
            settings.CSRF_COOKIE_NAME: csrf_2,
        },
        "headers_2": {"X-CSRF-Token": csrf_2},
    }


@pytest.mark.asyncio
async def test_codebase_lifecycle_and_indexing(async_client: AsyncClient, setup_codebase_users):
    client = async_client
    ctx = setup_codebase_users
    w1_id = ctx["w1"].id

    # 1. Create Codebase
    create_res = await client.post(
        f"/api/v1/workspaces/{w1_id}/codebases",
        json={"name": "Core-Backend", "repository_url": "https://github.com/example/repo", "default_branch": "main"},
        cookies=ctx["cookies_1"],
        headers=ctx["headers_1"],
    )
    assert create_res.status_code == 201
    cb_data = create_res.json()
    cb_id = cb_data["id"]
    assert cb_data["name"] == "Core-Backend"
    assert cb_data["is_indexed"] is False

    # 2. Upload and Index Archive
    zip_bytes = create_mock_repo_zip()
    upload_res = await client.post(
        f"/api/v1/workspaces/{w1_id}/codebases/{cb_id}/upload",
        files={"file": ("repo.zip", zip_bytes, "application/zip")},
        cookies=ctx["cookies_1"],
        headers=ctx["headers_1"],
    )
    assert upload_res.status_code == 202
    gen_data = upload_res.json()
    assert gen_data["status"] == "active"
    assert gen_data["total_files"] >= 2
    assert gen_data["total_symbols"] >= 2

    # 3. Check Indexing Status
    status_res = await client.get(
        f"/api/v1/workspaces/{w1_id}/codebases/{cb_id}/status",
        cookies=ctx["cookies_1"],
    )
    assert status_res.status_code == 200
    gens = status_res.json()
    assert len(gens) >= 1
    assert gens[0]["status"] == "active"

    # 4. List Files
    files_res = await client.get(
        f"/api/v1/workspaces/{w1_id}/codebases/{cb_id}/files",
        cookies=ctx["cookies_1"],
    )
    assert files_res.status_code == 200
    files_data = files_res.json()
    assert files_data["total"] >= 2

    # 5. List Symbols
    sym_res = await client.get(
        f"/api/v1/workspaces/{w1_id}/codebases/{cb_id}/symbols",
        cookies=ctx["cookies_1"],
    )
    assert sym_res.status_code == 200
    sym_data = sym_res.json()
    assert sym_data["total"] >= 2

    # 6. Search Codebase
    search_res = await client.post(
        f"/api/v1/workspaces/{w1_id}/codebases/{cb_id}/search",
        json={"query": "verify_token", "top_k": 5},
        cookies=ctx["cookies_1"],
    )
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert len(search_data["results"]) >= 1

    # 7. Query Codebase Q&A with Citations
    query_res = await client.post(
        f"/api/v1/workspaces/{w1_id}/codebases/{cb_id}/query",
        json={"query": "How does AuthService work?", "top_k": 5},
        cookies=ctx["cookies_1"],
        headers=ctx["headers_1"],
    )
    assert query_res.status_code == 200
    q_data = query_res.json()
    assert "AuthService" in q_data["answer"] or "tokens" in q_data["answer"]
    assert len(q_data["citations"]) >= 1
    assert q_data["citations"][0]["file_path"] == "src/auth.py"

    # 8. Workspace Isolation / IDOR Verification
    w2_id = ctx["w2"].id
    idor_res = await client.get(
        f"/api/v1/workspaces/{w1_id}/codebases/{cb_id}",
        cookies=ctx["cookies_2"],  # User 2 attempting to view User 1 codebase
    )
    assert idor_res.status_code == 404