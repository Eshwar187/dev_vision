"""GitHub Integration & Repository Synchronization Schema

Revision ID: 0006_github_integration
Revises: 0005_codebase_rag_schema
Create Date: 2026-09-21 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_github_integration"
down_revision: Union[str, None] = "0005_codebase_rag_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. github_oauth_states
    op.create_table(
        "github_oauth_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("nonce", sa.String(length=64), nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_verifier", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("nonce", name="uq_github_oauth_nonce"),
    )
    op.create_index("idx_github_oauth_nonce", "github_oauth_states", ["nonce"], unique=True)
    op.create_index("idx_github_oauth_exp", "github_oauth_states", ["expires_at"], unique=False)

    # 2. github_installations
    # Product invariant: One installation belongs to exactly one workspace
    op.create_table(
        "github_installations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("account_login", sa.String(length=255), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("account_type", sa.String(length=32), nullable=False),
        sa.Column("installer_github_user_id", sa.BigInteger(), nullable=False),
        sa.Column("installer_github_user_login", sa.String(length=255), nullable=False),
        sa.Column(
            "installed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("installation_id", name="uq_github_inst_global_id"),
    )
    op.create_index("idx_github_inst_ws", "github_installations", ["workspace_id"], unique=False)
    op.create_index("uq_github_inst_global_id", "github_installations", ["installation_id"], unique=True)

    # 3. github_repositories
    # Product invariant: One repository belongs to exactly one workspace
    op.create_table(
        "github_repositories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "github_installation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("github_installations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "codebase_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("codebases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("github_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=512), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=False),
        sa.Column("is_private", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "attached_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("github_repo_id", name="uq_github_repos_global_repo"),
        sa.UniqueConstraint("codebase_id", name="uq_github_repos_codebase"),
    )
    op.create_index("idx_github_repos_ws", "github_repositories", ["workspace_id"], unique=False)
    op.create_index("idx_github_repos_inst", "github_repositories", ["github_installation_id"], unique=False)
    op.create_index("idx_github_repos_full_name", "github_repositories", ["full_name"], unique=False)
    op.create_index("uq_github_repos_global_repo", "github_repositories", ["github_repo_id"], unique=True)

    # 4. github_sync_runs
    op.create_table(
        "github_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("github_repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requested_ref", sa.String(length=255), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("file_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("byte_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "triggered_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'resolving_commit', 'acquiring_lease', 'downloading', "
            "'ingesting', 'indexing', 'validating', 'activating', 'completed', 'failed')",
            name="ck_github_sync_status",
        ),
    )
    op.create_index("idx_github_sync_repo", "github_sync_runs", ["repository_id"], unique=False)
    op.create_index("idx_github_sync_ws_status", "github_sync_runs", ["workspace_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_table("github_sync_runs")
    op.drop_table("github_repositories")
    op.drop_table("github_installations")
    op.drop_table("github_oauth_states")
