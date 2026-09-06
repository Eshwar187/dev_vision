import uuid
from typing import Optional
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Document(Base):
    """
    Workspace-scoped document entity.
    Maintains metadata, cryptographic checksum, and storage reference.
    Enforces UNIQUE (workspace_id, checksum) at the database constraint level.
    """

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("status IN ('uploaded', 'processing', 'ready', 'failed')", name="ck_documents_status"),
        CheckConstraint("file_size > 0", name="ck_documents_file_size"),
        UniqueConstraint("workspace_id", "checksum", name="uq_documents_workspace_checksum"),
        Index("ix_documents_workspace_cursor", "workspace_id", "created_at", "id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    object_key: Mapped[str] = mapped_column(
        String(512),
        unique=True,
        index=True,
        nullable=False,
    )
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    checksum: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="uploaded",
    )
    active_generation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_index_generations.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    # Relationships
    workspace: Mapped["app.modules.workspaces.models.Workspace"] = relationship(
        "app.modules.workspaces.models.Workspace",
    )
    uploader: Mapped[Optional["app.modules.identity.models.User"]] = relationship(
        "app.modules.identity.models.User",
    )
    generations: Mapped[list["app.modules.rag.models.DocumentIndexGeneration"]] = relationship(
        "app.modules.rag.models.DocumentIndexGeneration",
        foreign_keys="app.modules.rag.models.DocumentIndexGeneration.document_id",
        back_populates="document",
        cascade="all, delete-orphan",
    )
    active_generation: Mapped[Optional["app.modules.rag.models.DocumentIndexGeneration"]] = relationship(
        "app.modules.rag.models.DocumentIndexGeneration",
        foreign_keys=[active_generation_id],
        post_update=True,
    )
