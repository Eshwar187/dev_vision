"""GitHub integration service orchestrating OAuth, repository discovery,
attachment, ref-to-SHA resolution, archive download, and Phase 7 ingestion.
"""

import asyncio
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
    ValidationException,
)
from app.modules.codebase.models import (
    Codebase,
    CodebaseIndexGeneration,
    CodebaseProcessingLease,
)
from app.modules.codebase.service import CodebaseService
from app.modules.github.client import GitHubClient
from app.modules.github.models import (
    GitHubInstallation,
    GitHubOAuthState,
    GitHubRepository,
    GitHubSyncRun,
)
from app.modules.github.state import GitHubStateManager

logger = structlog.get_logger(__name__)
settings = get_settings()

REF_PATTERN = re.compile(r"^[a-zA-Z0-9._/-]+$")


def validate_ref_syntax(ref: str) -> None:
    """Validate Git ref name syntax to prevent injection and path traversal."""
    if not ref or len(ref) > 255:
        raise ValidationException("Git ref must be between 1 and 255 characters.")
    if ".." in ref or ref.startswith("/") or ref.endswith("/") or ref.startswith("-") or ref.endswith(".lock"):
        raise ValidationException("Invalid Git ref syntax.")
    if not REF_PATTERN.match(ref):
        raise ValidationException("Git ref contains invalid characters.")


class GitHubService:
    def __init__(
        self,
        client: Optional[GitHubClient] = None,
        codebase_service: Optional[CodebaseService] = None,
    ):
        self.client = client or GitHubClient()
        self.codebase_service = codebase_service or CodebaseService()

    # -------------------------------------------------------------------------
    # OAuth Connect & Callback
    # -------------------------------------------------------------------------
    async def init_connect(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Tuple[str, str, datetime]:
        """Initiate GitHub App connection for a workspace.
        Mints PKCE challenge and signed state. Returns authorization URL.
        """
        signed_state, code_challenge, _ = await GitHubStateManager.create_state(
            session=session,
            workspace_id=workspace_id,
            user_id=user_id,
        )

        app_slug = settings.GITHUB_APP_SLUG or "devvision-ai"
        # The installation URL with state parameter.
        # When "Request user authorization (OAuth) during installation" is enabled in App settings,
        # GitHub forwards to user OAuth authorization during the installation handshake.
        auth_url = f"https://github.com/apps/{app_slug}/installations/new?state={signed_state}"

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=settings.GITHUB_OAUTH_STATE_EXPIRE_SECONDS)

        logger.info(
            "github_connect_initialized",
            workspace_id=str(workspace_id),
            user_id=str(user_id),
        )
        return auth_url, signed_state, expires_at

    async def handle_oauth_callback(
        self,
        session: AsyncSession,
        code: str,
        state: str,
        installation_id_param: Optional[int],
        current_user_id: uuid.UUID,
        redirect_uri: Optional[str] = None,
    ) -> GitHubInstallation:
        """Handle OAuth callback:
        1. Verifies and atomically consumes HMAC state.
        2. Exchanges code using stored code_verifier for an ephemeral user access token.
        3. Verifies authentic installer GitHub user identity.
        4. Verifies administrative authority over the installation.
        5. Independently verifies installation belongs to DevVision GitHub App.
        6. Persists installation enforcing global installation exclusivity.
        7. Purges user access token.
        """
        # 1. Verify and consume state (checks HMAC, expiry, user session, replay)
        state_record = await GitHubStateManager.verify_and_consume_state(
            session=session,
            signed_state=state,
            expected_user_id=current_user_id,
        )
        workspace_id = state_record.workspace_id

        # 2. Exchange OAuth code using stored PKCE code_verifier
        user_token = await self.client.exchange_oauth_code(
            code=code,
            code_verifier=state_record.code_verifier,
            redirect_uri=redirect_uri or settings.GITHUB_REDIRECT_URI,
        )

        try:
            # 3. Establish authentic GitHub user identity
            github_user = await self.client.get_authenticated_user(user_token)
            installer_github_user_id = github_user["id"]
            installer_github_user_login = github_user["login"]

            # If installation_id was not in callback query params, discover from user installations
            target_inst_id = installation_id_param
            if not target_inst_id:
                user_installations_res = await self.client.list_installation_repositories(0) # trigger fetch
                # or query user installations
                raise ValidationException("Missing installation_id in GitHub callback.")

            # 4. Verify administrative authority over installation (rejects read-only and write-only users)
            inst_metadata = await self.client.verify_user_installation_authority(
                user_token=user_token,
                installation_id=target_inst_id,
                installer_github_user=github_user,
            )

            # 5. Verify installation exists under this DevVision App
            await self.client.verify_app_installation_exists(target_inst_id)

            account = inst_metadata.get("account", {})
            account_id = account.get("id", 0)
            account_login = account.get("login", "")
            account_type = inst_metadata.get("target_type", account.get("type", "User"))

            # 6. Check global installation uniqueness: UNIQUE(installation_id)
            existing_stmt = select(GitHubInstallation).where(
                GitHubInstallation.installation_id == target_inst_id
            )
            existing_res = await session.execute(existing_stmt)
            existing_inst = existing_res.scalar_one_or_none()

            if existing_inst:
                if existing_inst.workspace_id != workspace_id:
                    raise ConflictException(
                        "This GitHub installation is already linked to another DevVision workspace."
                    )
                # Update existing record
                existing_inst.account_login = account_login
                existing_inst.account_id = account_id
                existing_inst.account_type = account_type
                existing_inst.installer_github_user_id = installer_github_user_id
                existing_inst.installer_github_user_login = installer_github_user_login
                existing_inst.installed_by_user_id = current_user_id
                await session.flush()
                installation = existing_inst
            else:
                installation = GitHubInstallation(
                    workspace_id=workspace_id,
                    installation_id=target_inst_id,
                    account_login=account_login,
                    account_id=account_id,
                    account_type=account_type,
                    installer_github_user_id=installer_github_user_id,
                    installer_github_user_login=installer_github_user_login,
                    installed_by_user_id=current_user_id,
                )
                session.add(installation)
                await session.flush()

            logger.info(
                "github_installation_bound",
                workspace_id=str(workspace_id),
                installation_id=target_inst_id,
                account=account_login,
            )
            return installation

        finally:
            # Explicit in-memory purge of user access token
            del user_token

    # -------------------------------------------------------------------------
    # Installation Management
    # -------------------------------------------------------------------------
    async def list_installations(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> List[GitHubInstallation]:
        """List all GitHub installations bound to this workspace."""
        stmt = (
            select(GitHubInstallation)
            .where(GitHubInstallation.workspace_id == workspace_id)
            .order_by(GitHubInstallation.created_at.desc())
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def delete_installation(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        installation_id: uuid.UUID,
    ) -> None:
        """Disconnect an installation. Fails if active repositories reference it."""
        stmt = select(GitHubInstallation).where(
            GitHubInstallation.id == installation_id,
            GitHubInstallation.workspace_id == workspace_id,
        )
        res = await session.execute(stmt)
        inst = res.scalar_one_or_none()
        if not inst:
            raise EntityNotFoundException("GitHub installation not found.")

        # Check for attached repositories
        repo_stmt = select(func.count()).select_from(GitHubRepository).where(
            GitHubRepository.github_installation_id == installation_id
        )
        repo_count = (await session.execute(repo_stmt)).scalar() or 0
        if repo_count > 0:
            raise ValidationException(
                "Cannot disconnect installation with attached repositories. Please detach all repositories first."
            )

        await session.delete(inst)
        await session.flush()
        logger.info("github_installation_deleted", installation_id=str(installation_id))

    # -------------------------------------------------------------------------
    # Repository Discovery & Attachment
    # -------------------------------------------------------------------------
    async def discover_repositories(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        """Discover repositories accessible to workspace installations.
        Annotates attachment status and archived state without leaking foreign workspace metadata.
        """
        installations = await self.list_installations(session, workspace_id)
        if not installations:
            return []

        # Query all currently attached repos in the platform to determine exclusivity status
        attached_stmt = select(GitHubRepository.github_repo_id, GitHubRepository.workspace_id)
        attached_rows = (await session.execute(attached_stmt)).all()
        attached_map = {row[0]: row[1] for row in attached_rows}

        discovered: List[Dict[str, Any]] = []

        for inst in installations:
            try:
                repos = await self.client.list_installation_repositories(inst.installation_id)
                for r in repos:
                    repo_id = r["id"]
                    is_archived = r.get("archived", False)

                    # Determine attachment status
                    if repo_id in attached_map:
                        if attached_map[repo_id] == workspace_id:
                            attachment_status = "attached_to_this_workspace"
                        else:
                            # Attached to another workspace -> mark unavailable without leaking tenant info
                            attachment_status = "unavailable"
                    else:
                        attachment_status = "unattached"

                    discovered.append({
                        "github_repo_id": repo_id,
                        "name": r["name"],
                        "full_name": r["full_name"],
                        "default_branch": r.get("default_branch", "main"),
                        "is_private": r.get("private", False),
                        "is_archived": is_archived,
                        "attachment_status": attachment_status,
                        "installation_id": inst.installation_id,
                        "installation_account": inst.account_login,
                    })
            except Exception as e:
                logger.error(
                    "github_discovery_error",
                    installation_id=inst.installation_id,
                    error=str(e),
                )

        return discovered

    async def attach_repository(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        github_repo_id: int,
    ) -> GitHubRepository:
        """Attach an authorized GitHub repository to a DevVision workspace.
        Enforces:
        - RBAC caller validation.
        - Verification that repo belongs to an active installation for this workspace.
        - Rejection of archived repositories.
        - Global repository exclusivity: UNIQUE(github_repo_id).
        - Creates Codebase and enqueues initial sync.
        """
        installations = await self.list_installations(session, workspace_id)
        if not installations:
            raise ValidationException("No active GitHub installations found in this workspace.")

        # Check global repository exclusivity: UNIQUE(github_repo_id)
        existing_stmt = select(GitHubRepository).where(GitHubRepository.github_repo_id == github_repo_id)
        existing_res = await session.execute(existing_stmt)
        if existing_res.scalar_one_or_none():
            raise ConflictException("This repository is already attached to a DevVision workspace.")

        # Verify repository exists and belongs to one of the workspace installations
        target_inst = None
        target_repo_data = None

        for inst in installations:
            repos = await self.client.list_installation_repositories(inst.installation_id)
            match = next((r for r in repos if r["id"] == github_repo_id), None)
            if match:
                target_inst = inst
                target_repo_data = match
                break

        if not target_inst or not target_repo_data:
            raise ValidationException("Repository not found in workspace installations.")

        # Check archived status
        if target_repo_data.get("archived", False):
            raise ValidationException("Archived repositories cannot be attached.")

        repo_name = target_repo_data["name"]
        repo_full_name = target_repo_data["full_name"]
        default_branch = target_repo_data.get("default_branch", "main")
        is_private = target_repo_data.get("private", False)
        repo_url = target_repo_data.get("html_url")

        # 1. Create Phase 7 Codebase record
        codebase = await self.codebase_service.create_codebase(
            session=session,
            workspace_id=workspace_id,
            name=repo_name,
            repository_url=repo_url,
            default_branch=default_branch,
        )

        # 2. Create GitHubRepository record
        gh_repo = GitHubRepository(
            workspace_id=workspace_id,
            github_installation_id=target_inst.id,
            codebase_id=codebase.id,
            github_repo_id=github_repo_id,
            name=repo_name,
            full_name=repo_full_name,
            default_branch=default_branch,
            is_private=is_private,
            is_archived=False,
            attached_by_user_id=user_id,
        )
        session.add(gh_repo)
        await session.flush()

        # 3. Create initial sync run in 'queued' state
        initial_sync = GitHubSyncRun(
            repository_id=gh_repo.id,
            workspace_id=workspace_id,
            requested_ref=default_branch,
            commit_sha=None,  # Nullable initially
            status="queued",
            file_count=0,
            byte_count=0,
            started_at=None,  # Nullable initially
            completed_at=None,
            triggered_by_user_id=user_id,
        )
        session.add(initial_sync)
        await session.flush()

        logger.info(
            "github_repository_attached",
            workspace_id=str(workspace_id),
            repo_id=str(gh_repo.id),
            full_name=repo_full_name,
        )
        return gh_repo

    async def detach_repository(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        repo_id: uuid.UUID,
    ) -> None:
        """Detach a repository and delete its linked Codebase (cascading cleanup)."""
        stmt = select(GitHubRepository).where(
            GitHubRepository.id == repo_id,
            GitHubRepository.workspace_id == workspace_id,
        )
        res = await session.execute(stmt)
        repo = res.scalar_one_or_none()
        if not repo:
            raise EntityNotFoundException("GitHub repository not found.")

        # Delete linked codebase; cascade handles generations, files, symbols, chunks, sync runs
        await self.codebase_service.delete_codebase(
            session=session,
            workspace_id=workspace_id,
            codebase_id=repo.codebase_id,
        )
        logger.info("github_repository_detached", repo_id=str(repo_id))

    async def get_repository_by_codebase_id(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        codebase_id: uuid.UUID,
    ) -> Optional[GitHubRepository]:
        """Fetch attached GitHub repository record associated with a codebase, if any."""
        stmt = select(GitHubRepository).where(
            GitHubRepository.codebase_id == codebase_id,
            GitHubRepository.workspace_id == workspace_id,
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # Synchronization Pipeline Execution
    # -------------------------------------------------------------------------
    async def create_sync_run(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        repo_id: uuid.UUID,
        ref: Optional[str] = None,
        force: bool = False,
    ) -> GitHubSyncRun:
        """Enqueue a synchronization run for a repository."""
        stmt = select(GitHubRepository).where(
            GitHubRepository.id == repo_id,
            GitHubRepository.workspace_id == workspace_id,
        )
        res = await session.execute(stmt)
        repo = res.scalar_one_or_none()
        if not repo:
            raise EntityNotFoundException("GitHub repository not found.")

        target_ref = ref.strip() if ref else repo.default_branch
        validate_ref_syntax(target_ref)

        sync_run = GitHubSyncRun(
            repository_id=repo.id,
            workspace_id=workspace_id,
            requested_ref=target_ref,
            commit_sha=None,
            status="queued",
            file_count=0,
            byte_count=0,
            started_at=None,
            completed_at=None,
            triggered_by_user_id=user_id,
        )
        session.add(sync_run)
        await session.flush()
        return sync_run

    async def execute_sync_run(
        self,
        session: AsyncSession,
        sync_run_id: uuid.UUID,
        force: bool = False,
    ) -> GitHubSyncRun:
        """Execute the full 9-stage sync state machine:
        queued -> resolving_commit -> acquiring_lease -> downloading -> ingesting -> indexing -> validating -> activating -> completed
        On error: -> failed (active generation preserved untouched).
        """
        # Fetch sync run
        stmt = select(GitHubSyncRun).where(GitHubSyncRun.id == sync_run_id).with_for_update()
        res = await session.execute(stmt)
        sync_run = res.scalar_one_or_none()
        if not sync_run:
            raise EntityNotFoundException("Sync run not found.")

        repo_stmt = select(GitHubRepository).where(GitHubRepository.id == sync_run.repository_id)
        repo = (await session.execute(repo_stmt)).scalar_one()

        inst_stmt = select(GitHubInstallation).where(GitHubInstallation.id == repo.github_installation_id)
        inst = (await session.execute(inst_stmt)).scalar_one()

        cb_stmt = select(Codebase).where(Codebase.id == repo.codebase_id)
        codebase = (await session.execute(cb_stmt)).scalar_one()

        sync_run.started_at = datetime.now(timezone.utc)
        sync_run.status = "resolving_commit"
        await session.flush()

        owner, repo_name = repo.full_name.split("/", 1)
        lease_acquired = False

        try:
            # Stage 1: Resolving Commit (mutable ref -> immutable SHA)
            commit_sha = await self.client.resolve_commit_sha(
                installation_id=inst.installation_id,
                owner=owner,
                repo=repo_name,
                ref=sync_run.requested_ref,
            )
            sync_run.commit_sha = commit_sha
            await session.flush()

            # Idempotency Check: if not force and active generation already has this commit_sha
            if not force and codebase.active_generation_id:
                gen_stmt = select(CodebaseIndexGeneration).where(
                    CodebaseIndexGeneration.id == codebase.active_generation_id
                )
                active_gen = (await session.execute(gen_stmt)).scalar_one_or_none()
                if active_gen and active_gen.commit_hash == commit_sha:
                    logger.info(
                        "github_sync_idempotent_noop",
                        codebase_id=str(codebase.id),
                        commit_sha=commit_sha,
                    )
                    sync_run.status = "completed"
                    sync_run.file_count = active_gen.total_files
                    sync_run.completed_at = datetime.now(timezone.utc)
                    await session.flush()
                    return sync_run

            # Stage 2: Acquiring Lease
            sync_run.status = "acquiring_lease"
            await session.flush()

            worker_id = f"worker-{uuid.uuid4().hex[:8]}"
            now = datetime.now(timezone.utc)
            lease_stmt = select(CodebaseProcessingLease).where(
                CodebaseProcessingLease.codebase_id == codebase.id
            ).with_for_update()
            lease_res = await session.execute(lease_stmt)
            lease = lease_res.scalar_one_or_none()

            if lease and lease.lease_expires_at > now:
                raise ConflictException("A synchronization job is already running for this codebase.")

            if lease:
                lease.fencing_token += 1
                lease.worker_id = worker_id
                lease.lease_acquired_at = now
                lease.lease_expires_at = now + timedelta(seconds=settings.RAG_PROCESSING_LEASE_SECONDS)
                lease.heartbeat_at = now
            else:
                lease = CodebaseProcessingLease(
                    codebase_id=codebase.id,
                    generation_id=uuid.uuid4(),  # temporary generation placeholder
                    workspace_id=codebase.workspace_id,
                    worker_id=worker_id,
                    fencing_token=1,
                    lease_acquired_at=now,
                    lease_expires_at=now + timedelta(seconds=settings.RAG_PROCESSING_LEASE_SECONDS),
                    heartbeat_at=now,
                )
                session.add(lease)
            await session.flush()
            lease_acquired = True

            # Stage 3: Downloading Archive (with SSRF defense, redirect checks, size limits)
            sync_run.status = "downloading"
            await session.flush()

            tarball_bytes = await self.client.download_tarball_archive(
                installation_id=inst.installation_id,
                owner=owner,
                repo=repo_name,
                commit_sha=commit_sha,
                max_bytes=settings.GITHUB_MAX_COMPRESSED_TARBALL_BYTES,
            )
            sync_run.byte_count = len(tarball_bytes)
            await session.flush()

            # Stage 4-8: Ingesting, Parsing, Chunking, Indexing (Authoritative Phase 7 Pipeline)
            sync_run.status = "indexing"
            await session.flush()

            # Execute Phase 7 authoritative pipeline
            new_generation = await self.codebase_service.index_archive(
                session=session,
                workspace_id=codebase.workspace_id,
                codebase_id=codebase.id,
                archive_bytes=tarball_bytes,
            )

            # Update generation commit hash provenance
            new_generation.commit_hash = commit_sha
            new_generation.branch = sync_run.requested_ref

            # Stage 9: Completing
            sync_run.status = "completed"
            sync_run.file_count = new_generation.total_files
            sync_run.completed_at = datetime.now(timezone.utc)
            await session.flush()

            logger.info(
                "github_sync_completed",
                sync_run_id=str(sync_run.id),
                commit_sha=commit_sha,
                total_files=new_generation.total_files,
            )
            return sync_run

        except Exception as e:
            logger.error("github_sync_failed", sync_run_id=str(sync_run_id), error=str(e))
            sync_run.status = "failed"
            sync_run.error_message = str(e)
            sync_run.completed_at = datetime.now(timezone.utc)
            await session.flush()
            raise

        finally:
            if lease_acquired:
                # Release lease
                del_lease = delete(CodebaseProcessingLease).where(
                    CodebaseProcessingLease.codebase_id == codebase.id
                )
                await session.execute(del_lease)
                await session.flush()

    async def list_sync_runs(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        repo_id: uuid.UUID,
    ) -> List[GitHubSyncRun]:
        """List historical sync runs for a repository."""
        stmt = (
            select(GitHubSyncRun)
            .where(
                GitHubSyncRun.repository_id == repo_id,
                GitHubSyncRun.workspace_id == workspace_id,
            )
            .order_by(GitHubSyncRun.created_at.desc())
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())
