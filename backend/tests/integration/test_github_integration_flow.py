"""Comprehensive integration tests for GitHub integration and synchronization flow."""

import io
import tarfile
import uuid
from unittest.mock import AsyncMock, patch
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, ValidationException
from app.modules.codebase.models import Codebase, CodebaseIndexGeneration
from app.modules.codebase.service import CodebaseService
from app.modules.github.client import GitHubClient
from app.modules.github.models import (
    GitHubInstallation,
    GitHubRepository,
    GitHubSyncRun,
)
from app.modules.github.service import GitHubService, validate_ref_syntax
from app.modules.identity.models import User
from app.modules.workspaces.models import Workspace


def create_mock_tarball() -> bytes:
    """Create an in-memory tarball archive with mock Python source."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        content = b"def calculate_total(items):\n    \"\"\"Calculate total sum.\"\"\"\n    return sum(items)\n"
        info = tarfile.TarInfo(name="org-repo-c1a2b3c4/math_utils.py")
        info.size = len(content)
        info.mtime = 1700000000
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


@pytest.fixture
def mock_github_client():
    client = GitHubClient()
    client.exchange_oauth_code = AsyncMock(return_value="ghu_test_user_token_abc123")
    client.get_authenticated_user = AsyncMock(return_value={"id": 1001, "login": "octocat"})
    client.verify_user_installation_authority = AsyncMock(
        return_value={
            "id": 998877,
            "target_type": "Organization",
            "account": {"id": 554433, "login": "octo-org", "type": "Organization"},
            "permissions": {"administration": "write"},
        }
    )
    client.verify_app_installation_exists = AsyncMock(return_value={"id": 998877})
    client.list_installation_repositories = AsyncMock(
        return_value=[
            {
                "id": 111222,
                "name": "core-backend",
                "full_name": "octo-org/core-backend",
                "default_branch": "main",
                "private": True,
                "archived": False,
                "html_url": "https://github.com/octo-org/core-backend",
            },
            {
                "id": 111333,
                "name": "legacy-tool",
                "full_name": "octo-org/legacy-tool",
                "default_branch": "master",
                "private": False,
                "archived": True,
                "html_url": "https://github.com/octo-org/legacy-tool",
            },
        ]
    )
    client.resolve_commit_sha = AsyncMock(return_value="a" * 40)
    client.download_tarball_archive = AsyncMock(return_value=create_mock_tarball())
    return client


@pytest.mark.asyncio
async def test_full_oauth_handshake_and_installation(
    db_session: AsyncSession,
    mock_github_client,
):
    """Test full OAuth handshake: init -> callback -> installation persistence."""
    # Setup test user and workspace
    user = User(email="dev@example.com", password_hash="hashed_pw", display_name="Dev User", is_active=True)
    db_session.add(user)
    await db_session.flush()

    workspace = Workspace(name="Engineering Workspace", slug="eng-ws", created_by=user.id)
    db_session.add(workspace)
    await db_session.flush()

    service = GitHubService(client=mock_github_client)

    # 1. Init connect
    auth_url, signed_state, expires_at = await service.init_connect(
        session=db_session,
        workspace_id=workspace.id,
        user_id=user.id,
    )
    assert "https://github.com/apps/" in auth_url
    assert signed_state in auth_url

    # 2. Callback
    installation = await service.handle_oauth_callback(
        session=db_session,
        code="mock_oauth_code_123",
        state=signed_state,
        installation_id_param=998877,
        current_user_id=user.id,
    )

    assert installation.installation_id == 998877
    assert installation.account_login == "octo-org"
    assert installation.installer_github_user_login == "octocat"
    assert installation.workspace_id == workspace.id


@pytest.mark.asyncio
async def test_global_installation_uniqueness_conflict(
    db_session: AsyncSession,
    mock_github_client,
):
    """Verify that linking an already-linked installation to a different workspace fails with ConflictException."""
    user = User(email="owner@example.com", password_hash="pw", display_name="Owner", is_active=True)
    db_session.add(user)
    await db_session.flush()

    ws1 = Workspace(name="Workspace 1", slug="ws-1", created_by=user.id)
    ws2 = Workspace(name="Workspace 2", slug="ws-2", created_by=user.id)
    db_session.add_all([ws1, ws2])
    await db_session.flush()

    service = GitHubService(client=mock_github_client)

    # Bind to Workspace 1
    _, state1, _ = await service.init_connect(db_session, ws1.id, user.id)
    await service.handle_oauth_callback(db_session, "code1", state1, 998877, user.id)

    # Attempt to bind same installation to Workspace 2
    _, state2, _ = await service.init_connect(db_session, ws2.id, user.id)
    with pytest.raises(ConflictException, match="already linked to another DevVision workspace"):
        await service.handle_oauth_callback(db_session, "code2", state2, 998877, user.id)


@pytest.mark.asyncio
async def test_repository_attachment_and_global_exclusivity(
    db_session: AsyncSession,
    mock_github_client,
):
    """Verify repository attachment, archived repo rejection, and global exclusivity."""
    user = User(email="lead@example.com", password_hash="pw", display_name="Lead", is_active=True)
    db_session.add(user)
    await db_session.flush()

    ws1 = Workspace(name="Team A", slug="team-a", created_by=user.id)
    ws2 = Workspace(name="Team B", slug="team-b", created_by=user.id)
    db_session.add_all([ws1, ws2])
    await db_session.flush()

    service = GitHubService(client=mock_github_client)

    # Setup installation on ws1
    _, state1, _ = await service.init_connect(db_session, ws1.id, user.id)
    await service.handle_oauth_callback(db_session, "code1", state1, 998877, user.id)

    # Setup installation on ws2
    mock_github_client.verify_user_installation_authority.return_value["id"] = 776655
    mock_github_client.verify_app_installation_exists.return_value["id"] = 776655
    _, state2, _ = await service.init_connect(db_session, ws2.id, user.id)
    await service.handle_oauth_callback(db_session, "code2", state2, 776655, user.id)

    # 1. Attempt to attach archived repo -> must fail
    with pytest.raises(ValidationException, match="Archived repositories cannot be attached"):
        await service.attach_repository(db_session, ws1.id, user.id, github_repo_id=111333)

    # 2. Attach active repo to ws1 -> success
    repo1 = await service.attach_repository(db_session, ws1.id, user.id, github_repo_id=111222)
    assert repo1.github_repo_id == 111222
    assert repo1.name == "core-backend"

    # Verify Codebase was created
    codebase_stmt = select(Codebase).where(Codebase.id == repo1.codebase_id)
    cb = (await db_session.execute(codebase_stmt)).scalar_one()
    assert cb.name == "core-backend"

    # 3. Attempt to attach same repo to ws2 -> must fail with ConflictException
    with pytest.raises(ConflictException, match="already attached to a DevVision workspace"):
        await service.attach_repository(db_session, ws2.id, user.id, github_repo_id=111222)


@pytest.mark.asyncio
async def test_synchronization_pipeline_and_idempotency(
    db_session: AsyncSession,
    mock_github_client,
):
    """Verify ref resolution, tarball extraction, Phase 7 indexing, and same-SHA idempotency."""
    user = User(email="sync@example.com", password_hash="pw", display_name="Sync User", is_active=True)
    db_session.add(user)
    await db_session.flush()

    ws = Workspace(name="Sync Workspace", slug="sync-ws", created_by=user.id)
    db_session.add(ws)
    await db_session.flush()

    codebase_service = CodebaseService()
    service = GitHubService(client=mock_github_client, codebase_service=codebase_service)

    # Setup installation & attach repo
    _, state, _ = await service.init_connect(db_session, ws.id, user.id)
    await service.handle_oauth_callback(db_session, "code", state, 998877, user.id)
    repo = await service.attach_repository(db_session, ws.id, user.id, 111222)

    # Initial sync run created by attachment
    sync_stmt = select(GitHubSyncRun).where(GitHubSyncRun.repository_id == repo.id)
    initial_sync = (await db_session.execute(sync_stmt)).scalar_one()
    assert initial_sync.status == "queued"
    assert initial_sync.commit_sha is None

    # Execute sync run
    completed_run = await service.execute_sync_run(db_session, initial_sync.id)
    assert completed_run.status == "completed"
    assert completed_run.commit_sha == "a" * 40
    assert completed_run.file_count > 0

    # Verify Codebase has active generation pointing to this commit
    cb_stmt = select(Codebase).where(Codebase.id == repo.codebase_id)
    codebase = (await db_session.execute(cb_stmt)).scalar_one()
    assert codebase.is_indexed is True
    assert codebase.active_generation_id is not None

    gen_stmt = select(CodebaseIndexGeneration).where(CodebaseIndexGeneration.id == codebase.active_generation_id)
    active_gen = (await db_session.execute(gen_stmt)).scalar_one()
    assert active_gen.commit_hash == "a" * 40
    assert active_gen.status == "active"

    # Idempotency Test: Trigger sync for same ref without force -> No-Op
    noop_sync = await service.create_sync_run(db_session, ws.id, user.id, repo.id, ref="main", force=False)
    noop_result = await service.execute_sync_run(db_session, noop_sync.id, force=False)
    assert noop_result.status == "completed"

    # Active generation ID remains untouched
    cb_check = (await db_session.execute(cb_stmt)).scalar_one()
    assert cb_check.active_generation_id == active_gen.id


def test_ref_syntax_validation():
    """Verify Git ref syntax validation blocks injection and directory traversal."""
    # Valid refs
    validate_ref_syntax("main")
    validate_ref_syntax("release/v1.0.0")
    validate_ref_syntax("feature-branch_2")
    validate_ref_syntax("tags/v2.1")

    # Invalid refs
    with pytest.raises(ValidationException, match="Invalid Git ref syntax"):
        validate_ref_syntax("../etc/passwd")

    with pytest.raises(ValidationException, match="Invalid Git ref syntax"):
        validate_ref_syntax("/root/branch")

    with pytest.raises(ValidationException, match="Invalid Git ref syntax"):
        validate_ref_syntax("-flag")

    with pytest.raises(ValidationException, match="Invalid Git ref syntax"):
        validate_ref_syntax("branch.lock")

    with pytest.raises(ValidationException, match="Invalid Git ref syntax"):
        validate_ref_syntax("main;rm -rf /")
