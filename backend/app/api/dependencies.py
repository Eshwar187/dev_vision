import uuid
from typing import Callable, List
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import (
    AuthenticationException,
    AuthorizationException,
    CSRFException,
    UserInactiveException,
    WorkspaceNotFoundException,
)
from app.core.security import hash_session_token, verify_csrf_tokens
from app.modules.identity.models import User
from app.modules.identity.service import IdentityService
from app.modules.workspaces.models import Workspace, WorkspaceMembership
from sqlalchemy import select

settings = get_settings()


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Authenticates user via HttpOnly session cookie.
    Extracts raw token, hashes with SHA-256, and verifies against database.
    Rejects expired or missing sessions with 401 UNAUTHENTICATED.
    """
    session_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_token:
        raise AuthenticationException("Authentication cookie missing.")

    token_hash = hash_session_token(session_token)
    user = await IdentityService.get_user_by_session_hash(db, token_hash)
    if not user:
        raise AuthenticationException("Invalid or expired session.")

    request.state.user = user
    request.state.session_token_hash = token_hash
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Verifies that the authenticated user account is active."""
    if not current_user.is_active:
        raise UserInactiveException()
    return current_user


async def verify_csrf_token(request: Request) -> None:
    """
    Explicit CSRF Protection for state-changing HTTP methods (POST, PUT, PATCH, DELETE).
    Compares the devvision_csrf cookie with the X-CSRF-Token header in constant time.
    Safe methods (GET, HEAD, OPTIONS) bypass CSRF validation.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    csrf_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME)
    csrf_header = request.headers.get("X-CSRF-Token")

    if not verify_csrf_tokens(csrf_header, csrf_cookie):
        raise CSRFException()


async def get_current_workspace(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Workspace:
    """Validates existence of a workspace."""
    workspace = await db.scalar(select(Workspace).where(Workspace.id == workspace_id))
    if not workspace:
        raise WorkspaceNotFoundException()
    return workspace


async def require_workspace_member(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMembership:
    """
    Verifies that the current user is an active member of the target workspace.
    IDOR Defense: Returns 404 WORKSPACE_NOT_FOUND (instead of 403) if the user is not a member,
    preventing non-members from inferring the existence of private workspaces.
    """
    membership = await db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == current_user.id,
        )
    )
    if not membership:
        raise WorkspaceNotFoundException()
    return membership


def require_workspace_role(*allowed_roles: str) -> Callable:
    """
    Role-Based Access Control dependency factory.
    Enforces that the user's role in the workspace is within allowed_roles.
    """
    async def role_checker(
        membership: WorkspaceMembership = Depends(require_workspace_member),
    ) -> WorkspaceMembership:
        if membership.role not in allowed_roles:
            raise AuthorizationException("Insufficient permissions in this workspace.")
        return membership

    return role_checker