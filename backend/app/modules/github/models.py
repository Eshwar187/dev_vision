import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class GitHubOAuthState(Base):
    """Short-lived OAuth state and PKCE verifier tracking."""
    __tablename__ = "github_oauth_states"
    __table_args__ = (
        Index("idx_github_oauth_nonce", "nonce"),
        Index("idx_github_oauth_exp", "expires_at"),
    )

    nonce: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    code_verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class GitHubInstallation(Base):
    """GitHub App Installation associated with a DevVision Workspace.
    PRODUCT INVARIANT: One installation belongs to exactly one DevVision workspace.
    """
    __tablename__ = "github_installations"
    __table_args__ = (
        Index("idx_github_inst_ws", "workspace_id"),
        UniqueConstraint("installation_id", name="uq_github_inst_global_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    installation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    account_login: Mapped[str] = mapped_column(String(255), nullable=False)
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 'User' or 'Organization'
    installer_github_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    installer_github_user_login: Mapped[str] = mapped_column(String(255), nullable=False)
    installed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    repositories: Mapped[List["GitHubRepository"]] = relationship(
        "GitHubRepository",
        back_populates="installation",
        cascade="all, delete-orphan",
    )


class GitHubRepository(Base):
    """GitHub Repository attached to a DevVision Workspace.
    PRODUCT INVARIANT: One GitHub repository belongs to exactly one DevVision workspace.
    """
    __tablename__ = "github_repositories"
    __table_args__ = (
        Index("idx_github_repos_ws", "workspace_id"),
        Index("idx_github_repos_inst", "github_installation_id"),
        Index("idx_github_repos_full_name", "full_name"),
        UniqueConstraint("github_repo_id", name="uq_github_repos_global_repo"),
        UniqueConstraint("codebase_id", name="uq_github_repos_codebase"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    github_installation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("github_installations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    codebase_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("codebases.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    github_repo_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attached_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    installation: Mapped["GitHubInstallation"] = relationship(
        "GitHubInstallation",
        back_populates="repositories",
    )
    sync_runs: Mapped[List["GitHubSyncRun"]] = relationship(
        "GitHubSyncRun",
        back_populates="repository",
        cascade="all, delete-orphan",
    )


class GitHubSyncRun(Base):
    """Execution history of repository synchronizations.
    Supports queued/resolving state: commit_sha, started_at, and completed_at are nullable initially.
    """
    __tablename__ = "github_sync_runs"
    __table_args__ = (
        Index("idx_github_sync_repo", "repository_id"),
        Index("idx_github_sync_ws_status", "workspace_id", "status"),
        CheckConstraint(
            "status IN ('queued', 'resolving_commit', 'acquiring_lease', 'downloading', "
            "'ingesting', 'indexing', 'validating', 'activating', 'completed', 'failed')",
            name="ck_github_sync_status",
        ),
    )

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("github_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    repository: Mapped["GitHubRepository"] = relationship(
        "GitHubRepository",
        back_populates="sync_runs",
    )
