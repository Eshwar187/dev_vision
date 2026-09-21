import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_active_user,
    get_db,
    require_workspace_member,
    require_workspace_role,
    verify_csrf_token,
)
from app.modules.github.schemas import (
    GitHubConnectInitResponse,
    GitHubDiscoveredRepoListResponse,
    GitHubInstallationListResponse,
    GitHubInstallationSummary,
    GitHubRepoAttachRequest,
    GitHubRepositorySummary,
    GitHubSyncRequest,
    GitHubSyncRunListResponse,
    GitHubSyncRunSummary,
)
from app.modules.github.service import GitHubService
from app.modules.identity.models import User
from app.modules.workspaces.models import WorkspaceMembership

router = APIRouter()
callback_router = APIRouter()
_github_service_instance: Optional[GitHubService] = None


def get_github_service() -> GitHubService:
    global _github_service_instance
    if _github_service_instance is None:
        _github_service_instance = GitHubService()
    return _github_service_instance


# -----------------------------------------------------------------------------
# OAuth Handshake Endpoints
# -----------------------------------------------------------------------------
@router.post(
    "/{workspace_id}/github/connect/init",
    response_model=GitHubConnectInitResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_csrf_token)],
)
async def init_github_connect(
    workspace_id: uuid.UUID,
    membership: WorkspaceMembership = Depends(require_workspace_role(["owner", "admin"])),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
    github_service: GitHubService = Depends(get_github_service),
) -> GitHubConnectInitResponse:
    """Initialize GitHub App installation + OAuth handshake with PKCE and HMAC state."""
    auth_url, signed_state, expires_at = await github_service.init_connect(
        session=session,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )
    return GitHubConnectInitResponse(
        authorization_url=auth_url,
        state=signed_state,
        expires_at=expires_at,
    )


@callback_router.get(
    "/github/callback",
    status_code=status.HTTP_200_OK,
)
async def github_oauth_callback(
    code: str = Query(..., description="GitHub OAuth authorization code"),
    state: str = Query(..., description="HMAC-signed state token"),
    installation_id: Optional[int] = Query(None, description="GitHub App installation ID"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
    github_service: GitHubService = Depends(get_github_service),
):
    """Handle GitHub App OAuth callback:
    Verifies state, exchanges code with PKCE, proves installer identity & admin authority,
    and binds the installation record.
    """
    installation = await github_service.handle_oauth_callback(
        session=session,
        code=code,
        state=state,
        installation_id_param=installation_id,
        current_user_id=current_user.id,
    )
    # Redirect back to frontend workspace settings tab
    return RedirectResponse(
        url=f"/workspaces?github_connected=true&installation_id={installation.installation_id}",
        status_code=status.HTTP_302_FOUND,
    )


# -----------------------------------------------------------------------------
# Installation Management Endpoints
# -----------------------------------------------------------------------------
@router.get(
    "/{workspace_id}/github/installations",
    response_model=GitHubInstallationListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_installations(
    workspace_id: uuid.UUID,
    membership: WorkspaceMembership = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
    github_service: GitHubService = Depends(get_github_service),
) -> GitHubInstallationListResponse:
    """List connected GitHub installations for this workspace."""
    items = await github_service.list_installations(session, workspace_id)
    return GitHubInstallationListResponse(
        items=[GitHubInstallationSummary.model_validate(item) for item in items]
    )


@router.delete(
    "/{workspace_id}/github/installations/{installation_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_csrf_token)],
)
async def delete_installation(
    workspace_id: uuid.UUID,
    installation_id: uuid.UUID,
    membership: WorkspaceMembership = Depends(require_workspace_role(["owner", "admin"])),
    session: AsyncSession = Depends(get_db),
    github_service: GitHubService = Depends(get_github_service),
):
    """Disconnect a GitHub installation from this workspace."""
    await github_service.delete_installation(session, workspace_id, installation_id)
    return {"message": "Installation disconnected successfully."}


# -----------------------------------------------------------------------------
# Repository Discovery & Attachment Endpoints
# -----------------------------------------------------------------------------
@router.get(
    "/{workspace_id}/github/repositories",
    response_model=GitHubDiscoveredRepoListResponse,
    status_code=status.HTTP_200_OK,
)
async def discover_repositories(
    workspace_id: uuid.UUID,
    membership: WorkspaceMembership = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
    github_service: GitHubService = Depends(get_github_service),
) -> GitHubDiscoveredRepoListResponse:
    """Discover repositories accessible to workspace installations."""
    items = await github_service.discover_repositories(session, workspace_id)
    return GitHubDiscoveredRepoListResponse(items=items)


@router.post(
    "/{workspace_id}/github/repositories/attach",
    response_model=GitHubRepositorySummary,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf_token)],
)
async def attach_repository(
    workspace_id: uuid.UUID,
    payload: GitHubRepoAttachRequest,
    membership: WorkspaceMembership = Depends(require_workspace_role(["owner", "admin"])),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
    github_service: GitHubService = Depends(get_github_service),
) -> GitHubRepositorySummary:
    """Attach an accessible GitHub repository to this workspace under global exclusivity."""
    repo = await github_service.attach_repository(
        session=session,
        workspace_id=workspace_id,
        user_id=current_user.id,
        github_repo_id=payload.github_repo_id,
    )
    return GitHubRepositorySummary.model_validate(repo)


@router.get(
    "/{workspace_id}/github/repositories/by-codebase/{codebase_id}",
    response_model=Optional[GitHubRepositorySummary],
    status_code=status.HTTP_200_OK,
)
async def get_repository_by_codebase(
    workspace_id: uuid.UUID,
    codebase_id: uuid.UUID,
    membership: WorkspaceMembership = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
    github_service: GitHubService = Depends(get_github_service),
) -> Optional[GitHubRepositorySummary]:
    """Get attached GitHub repository details for a given codebase ID, if connected."""
    repo = await github_service.get_repository_by_codebase_id(session, workspace_id, codebase_id)
    if not repo:
        return None
    return GitHubRepositorySummary.model_validate(repo)


@router.delete(
    "/{workspace_id}/github/repositories/{repo_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_csrf_token)],
)
async def detach_repository(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    membership: WorkspaceMembership = Depends(require_workspace_role(["owner", "admin"])),
    session: AsyncSession = Depends(get_db),
    github_service: GitHubService = Depends(get_github_service),
):
    """Detach a repository from this workspace and remove its associated Codebase."""
    await github_service.detach_repository(session, workspace_id, repo_id)
    return {"message": "Repository detached successfully."}


# -----------------------------------------------------------------------------
# Synchronization Endpoints
# -----------------------------------------------------------------------------
@router.post(
    "/{workspace_id}/github/repositories/{repo_id}/sync",
    response_model=GitHubSyncRunSummary,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_csrf_token)],
)
async def trigger_repository_sync(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    payload: GitHubSyncRequest,
    membership: WorkspaceMembership = Depends(require_workspace_role(["owner", "admin"])),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
    github_service: GitHubService = Depends(get_github_service),
) -> GitHubSyncRunSummary:
    """Enqueue and execute a synchronization run for an attached GitHub repository."""
    sync_run = await github_service.create_sync_run(
        session=session,
        workspace_id=workspace_id,
        user_id=current_user.id,
        repo_id=repo_id,
        ref=payload.ref,
        force=payload.force,
    )

    # Execute sync run
    completed_run = await github_service.execute_sync_run(
        session=session,
        sync_run_id=sync_run.id,
        force=payload.force,
    )
    return GitHubSyncRunSummary.model_validate(completed_run)


@router.get(
    "/{workspace_id}/github/repositories/{repo_id}/syncs",
    response_model=GitHubSyncRunListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_repository_syncs(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    membership: WorkspaceMembership = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
    github_service: GitHubService = Depends(get_github_service),
) -> GitHubSyncRunListResponse:
    """List historical synchronization runs for a repository."""
    runs = await github_service.list_sync_runs(session, workspace_id, repo_id)
    return GitHubSyncRunListResponse(
        items=[GitHubSyncRunSummary.model_validate(r) for r in runs]
    )
