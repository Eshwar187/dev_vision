import uuid
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import (
    get_current_active_user,
    require_workspace_member,
    require_workspace_role,
    verify_csrf_token,
)
from app.core.database import get_db
from app.core.exceptions import AuthorizationException
from app.modules.identity.models import User
from app.modules.workspaces.models import WorkspaceMembership
from app.modules.workspaces.schemas import (
    MemberAddRequest,
    MemberRoleUpdateRequest,
    TransferOwnershipRequest,
    WorkspaceCreateRequest,
    WorkspaceDetailResponse,
    WorkspaceMemberListResponse,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)
from app.modules.workspaces.service import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf_token)],
    summary="Create a new workspace",
)
async def create_workspace(
    data: WorkspaceCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    workspace, role = await WorkspaceService.create_workspace(
        db=db,
        user_id=current_user.id,
        name=data.name,
    )
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        created_by=workspace.created_by,
        role=role,
        created_at=workspace.created_at,
    )


@router.get(
    "",
    response_model=List[WorkspaceResponse],
    summary="List current user's workspaces",
)
async def list_workspaces(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[WorkspaceResponse]:
    rows = await WorkspaceService.list_user_workspaces(db=db, user_id=current_user.id)
    return [
        WorkspaceResponse(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            created_by=workspace.created_by,
            role=role,
            created_at=workspace.created_at,
        )
        for workspace, role in rows
    ]


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceDetailResponse,
    summary="Get single workspace details",
)
async def get_workspace(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceDetailResponse:
    workspace, role, member_count = await WorkspaceService.get_workspace_for_member(
        db=db,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )
    return WorkspaceDetailResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        created_by=workspace.created_by,
        role=role,
        member_count=member_count,
        created_at=workspace.created_at,
    )


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    dependencies=[Depends(verify_csrf_token)],
    summary="Update workspace name",
)
async def update_workspace(
    workspace_id: uuid.UUID,
    data: WorkspaceUpdateRequest,
    membership: WorkspaceMembership = Depends(require_workspace_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    workspace = await WorkspaceService.update_workspace(
        db=db,
        workspace_id=workspace_id,
        name=data.name,
    )
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        created_by=workspace.created_by,
        role=membership.role,
        created_at=workspace.created_at,
    )


@router.delete(
    "/{workspace_id}",
    dependencies=[Depends(verify_csrf_token)],
    summary="Delete workspace (Owner only)",
)
async def delete_workspace(
    workspace_id: uuid.UUID,
    membership: WorkspaceMembership = Depends(require_workspace_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    await WorkspaceService.delete_workspace(db=db, workspace_id=workspace_id)
    return {"status": "ok", "message": "Workspace deleted successfully."}


@router.get(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberListResponse,
    summary="List workspace members",
)
async def list_members(
    workspace_id: uuid.UUID,
    membership: WorkspaceMembership = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMemberListResponse:
    members = await WorkspaceService.list_members(db=db, workspace_id=workspace_id)
    return WorkspaceMemberListResponse(members=members)


@router.post(
    "/{workspace_id}/members",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf_token)],
    summary="Add an existing registered user to workspace",
)
async def add_member(
    workspace_id: uuid.UUID,
    data: MemberAddRequest,
    membership: WorkspaceMembership = Depends(require_workspace_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    new_member = await WorkspaceService.add_existing_member(
        db=db,
        workspace_id=workspace_id,
        email=data.email,
        role=data.role,
    )
    return {
        "status": "ok",
        "message": "Member added successfully.",
        "user_id": new_member.user_id,
        "workspace_id": new_member.workspace_id,
        "role": new_member.role,
    }


@router.patch(
    "/{workspace_id}/members/{user_id}",
    dependencies=[Depends(verify_csrf_token)],
    summary="Update member role (Owner only, last-owner invariant protected)",
)
async def update_member_role(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    data: MemberRoleUpdateRequest,
    membership: WorkspaceMembership = Depends(require_workspace_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    updated = await WorkspaceService.update_member_role(
        db=db,
        workspace_id=workspace_id,
        target_user_id=user_id,
        new_role=data.role,
    )
    return {
        "status": "ok",
        "message": "Role updated successfully.",
        "user_id": updated.user_id,
        "role": updated.role,
    }


@router.delete(
    "/{workspace_id}/members/{user_id}",
    dependencies=[Depends(verify_csrf_token)],
    summary="Remove member from workspace (Owner/Admin or self, last-owner protected)",
)
async def remove_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    # Permitted if:
    # 1. Caller is removing self
    # 2. Caller is owner
    # 3. Caller is admin removing a regular member (not an owner/admin)
    is_self = (current_user.id == user_id)
    is_owner = (membership.role == "owner")
    is_admin = (membership.role == "admin")

    if not (is_self or is_owner or is_admin):
        raise AuthorizationException("You do not have permission to remove members.")

    await WorkspaceService.remove_member(
        db=db,
        workspace_id=workspace_id,
        target_user_id=user_id,
    )
    return {"status": "ok", "message": "Member removed successfully."}


@router.post(
    "/{workspace_id}/transfer-ownership",
    dependencies=[Depends(verify_csrf_token)],
    summary="Atomically transfer workspace ownership (Owner only)",
)
async def transfer_ownership(
    workspace_id: uuid.UUID,
    data: TransferOwnershipRequest,
    current_user: User = Depends(get_current_active_user),
    membership: WorkspaceMembership = Depends(require_workspace_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    await WorkspaceService.transfer_ownership(
        db=db,
        workspace_id=workspace_id,
        current_owner_id=current_user.id,
        new_owner_user_id=data.new_owner_user_id,
    )
    return {"status": "ok", "message": "Workspace ownership transferred successfully."}