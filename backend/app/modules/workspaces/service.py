import uuid
from typing import Dict, List, Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import (
    LastOwnerException,
    MemberAlreadyExistsException,
    OwnershipTransferException,
    UserNotFoundException,
    WorkspaceNotFoundException,
)
from app.core.logging import get_logger
from app.core.security import normalize_email
from app.modules.identity.models import User
from app.modules.workspaces.models import Workspace, WorkspaceMembership

logger = get_logger("workspaces.service")


class WorkspaceService:
    """Service managing workspaces, tenant boundaries, and RBAC memberships."""

    @staticmethod
    def _generate_slug(base_name: str) -> str:
        cleaned = "".join(c if c.isalnum() else "-" for c in base_name.lower())
        slug = "-".join(part for part in cleaned.split("-") if part)
        return slug or "workspace"

    @classmethod
    async def _resolve_unique_slug(cls, db: AsyncSession, base_slug: str) -> str:
        slug = base_slug
        counter = 1
        while True:
            existing = await db.scalar(select(Workspace.id).where(Workspace.slug == slug))
            if not existing:
                return slug
            slug = f"{base_slug}-{counter}"
            counter += 1

    @classmethod
    async def create_workspace(cls, db: AsyncSession, user_id: uuid.UUID, name: str) -> Tuple[Workspace, str]:
        """Creates a new workspace and sets the creator as owner."""
        base_slug = cls._generate_slug(name)
        slug = await cls._resolve_unique_slug(db, base_slug)

        workspace = Workspace(
            name=name.strip(),
            slug=slug,
            created_by=user_id,
        )
        db.add(workspace)
        await db.flush()

        membership = WorkspaceMembership(
            user_id=user_id,
            workspace_id=workspace.id,
            role="owner",
        )
        db.add(membership)
        await db.commit()
        await db.refresh(workspace)

        logger.info("Workspace created", workspace_id=str(workspace.id), owner_id=str(user_id))
        return workspace, "owner"

    @classmethod
    async def list_user_workspaces(cls, db: AsyncSession, user_id: uuid.UUID) -> List[Tuple[Workspace, str]]:
        """Lists all workspaces in which the user holds membership."""
        result = await db.execute(
            select(Workspace, WorkspaceMembership.role)
            .join(WorkspaceMembership, Workspace.id == WorkspaceMembership.workspace_id)
            .where(WorkspaceMembership.user_id == user_id)
            .order_by(Workspace.created_at.desc())
        )
        return list(result.all())

    @classmethod
    async def get_workspace_for_member(
        cls, db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> Tuple[Workspace, str, int]:
        """
        Retrieves workspace and member count if the user is a member.
        IDOR Defense: returns 404 if user is not a member or workspace does not exist.
        """
        # Check membership
        membership = await db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
            )
        )
        if not membership:
            raise WorkspaceNotFoundException()

        workspace = await db.scalar(select(Workspace).where(Workspace.id == workspace_id))
        if not workspace:
            raise WorkspaceNotFoundException()

        member_count = await db.scalar(
            select(func.count(WorkspaceMembership.id)).where(WorkspaceMembership.workspace_id == workspace_id)
        ) or 1

        return workspace, membership.role, member_count

    @classmethod
    async def update_workspace(cls, db: AsyncSession, workspace_id: uuid.UUID, name: str) -> Workspace:
        """Updates workspace name."""
        workspace = await db.scalar(select(Workspace).where(Workspace.id == workspace_id))
        if not workspace:
            raise WorkspaceNotFoundException()

        workspace.name = name.strip()
        await db.commit()
        await db.refresh(workspace)
        return workspace

    @classmethod
    async def delete_workspace(cls, db: AsyncSession, workspace_id: uuid.UUID) -> None:
        """Deletes workspace, cascading memberships."""
        workspace = await db.scalar(select(Workspace).where(Workspace.id == workspace_id))
        if not workspace:
            raise WorkspaceNotFoundException()

        await db.delete(workspace)
        await db.commit()
        logger.info("Workspace deleted", workspace_id=str(workspace_id))

    @classmethod
    async def list_members(cls, db: AsyncSession, workspace_id: uuid.UUID) -> List[Dict]:
        """Lists all members of a workspace."""
        result = await db.execute(
            select(WorkspaceMembership, User)
            .join(User, WorkspaceMembership.user_id == User.id)
            .where(WorkspaceMembership.workspace_id == workspace_id)
            .order_by(WorkspaceMembership.created_at.asc())
        )
        members = []
        for membership, user in result.all():
            members.append(
                {
                    "user_id": user.id,
                    "email": user.email,
                    "display_name": user.display_name,
                    "role": membership.role,
                    "joined_at": membership.created_at,
                }
            )
        return members

    @classmethod
    async def add_existing_member(
        cls, db: AsyncSession, workspace_id: uuid.UUID, email: str, role: str
    ) -> WorkspaceMembership:
        """Adds an existing registered user to the workspace."""
        normalized = normalize_email(email)
        user = await db.scalar(select(User).where(User.email == normalized))
        if not user:
            raise UserNotFoundException(message="No registered user found with this email address.")

        existing_membership = await db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user.id,
            )
        )
        if existing_membership:
            raise MemberAlreadyExistsException()

        membership = WorkspaceMembership(
            user_id=user.id,
            workspace_id=workspace_id,
            role=role,
        )
        db.add(membership)
        await db.commit()
        await db.refresh(membership)
        logger.info("Member added to workspace", workspace_id=str(workspace_id), user_id=str(user.id), role=role)
        return membership

    @classmethod
    async def update_member_role(
        cls, db: AsyncSession, workspace_id: uuid.UUID, target_user_id: uuid.UUID, new_role: str
    ) -> WorkspaceMembership:
        """Updates role of an existing member, enforcing last-owner invariant."""
        membership = await db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == target_user_id,
            )
        )
        if not membership:
            raise UserNotFoundException(message="Member not found in this workspace.")

        # Last Owner Protection: Cannot demote the only owner
        if membership.role == "owner" and new_role != "owner":
            owner_count = await db.scalar(
                select(func.count(WorkspaceMembership.id)).where(
                    WorkspaceMembership.workspace_id == workspace_id,
                    WorkspaceMembership.role == "owner",
                )
            )
            if owner_count <= 1:
                raise LastOwnerException("Cannot demote the only owner of the workspace.")

        membership.role = new_role
        await db.commit()
        await db.refresh(membership)
        return membership

    @classmethod
    async def remove_member(cls, db: AsyncSession, workspace_id: uuid.UUID, target_user_id: uuid.UUID) -> None:
        """Removes a member from the workspace, enforcing last-owner invariant."""
        membership = await db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == target_user_id,
            )
        )
        if not membership:
            raise UserNotFoundException(message="Member not found in this workspace.")

        # Last Owner Protection: Cannot remove the only owner
        if membership.role == "owner":
            owner_count = await db.scalar(
                select(func.count(WorkspaceMembership.id)).where(
                    WorkspaceMembership.workspace_id == workspace_id,
                    WorkspaceMembership.role == "owner",
                )
            )
            if owner_count <= 1:
                raise LastOwnerException("Cannot remove the only owner from the workspace.")

        await db.delete(membership)
        await db.commit()
        logger.info("Member removed from workspace", workspace_id=str(workspace_id), user_id=str(target_user_id))

    @classmethod
    async def transfer_ownership(
        cls, db: AsyncSession, workspace_id: uuid.UUID, current_owner_id: uuid.UUID, new_owner_user_id: uuid.UUID
    ) -> None:
        """
        Atomically transfers workspace ownership.
        Promotes target member to owner and demotes current owner to admin.
        """
        if current_owner_id == new_owner_user_id:
            raise OwnershipTransferException("Cannot transfer ownership to yourself.")

        # Verify target is already a member
        target_membership = await db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == new_owner_user_id,
            )
        )
        if not target_membership:
            raise OwnershipTransferException("Target user must already be a member of the workspace.")

        caller_membership = await db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == current_owner_id,
            )
        )
        if not caller_membership or caller_membership.role != "owner":
            raise OwnershipTransferException("Only an existing owner can transfer workspace ownership.")

        # Atomic role swap
        target_membership.role = "owner"
        caller_membership.role = "admin"

        await db.commit()
        logger.info(
            "Ownership transferred",
            workspace_id=str(workspace_id),
            previous_owner=str(current_owner_id),
            new_owner=str(new_owner_user_id),
        )