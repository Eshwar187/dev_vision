"""Document management schema

Revision ID: 0003_document_management
Revises: 0002_identity_and_workspaces
Create Date: 2026-09-05 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_document_management"
down_revision: Union[str, None] = "0002_identity_and_workspaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="uploaded", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('uploaded', 'processing', 'ready', 'failed')", name="ck_documents_status"),
        sa.CheckConstraint("file_size > 0", name="ck_documents_file_size"),
        sa.UniqueConstraint("workspace_id", "checksum", name="uq_documents_workspace_checksum"),
    )
    op.create_index("ix_documents_workspace_id", "documents", ["workspace_id"], unique=False)
    op.create_index("ix_documents_uploaded_by", "documents", ["uploaded_by"], unique=False)
    op.create_index("ix_documents_object_key", "documents", ["object_key"], unique=True)
    op.create_index("ix_documents_checksum", "documents", ["checksum"], unique=False)
    op.create_index(
        "ix_documents_workspace_cursor",
        "documents",
        ["workspace_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("documents")
