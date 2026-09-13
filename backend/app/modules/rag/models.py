import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.core.database import Base


class DocumentIndexGeneration(Base):
    """
    Tracks indexing lifecycle generations per document.
    Allows zero-downtime re-indexing where active generation continues serving queries
    while a new generation builds in the background.
    """

    __tablename__ = "document_index_generations"
    __table_args__ = (
        UniqueConstraint("document_id", "generation_number", name="uq_doc_generation"),
        Index("idx_doc_index_gen_workspace", "workspace_id"),
        Index("idx_doc_index_gen_status", "document_id", "status"),
        Index(
            "uq_doc_single_active_gen",
            "document_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    generation_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="building",  # 'building', 'active', 'retired', 'failed'
    )
    stage: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="extracting",  # 'extracting', 'chunking', 'embedding', 'indexing', 'ready', 'failed'
    )
    pipeline_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="v1.0",
    )
    chunking_strategy: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="recursive_structural",
    )
    chunk_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=500,
    )
    chunk_overlap: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=50,
    )
    tokenizer_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="BAAI/bge-small-en-v1.5",
    )
    total_chunks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    unextractable_pages: Mapped[List[int]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    activated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    retired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    document: Mapped["app.modules.documents.models.Document"] = relationship(
        "app.modules.documents.models.Document",
        foreign_keys=[document_id],
        back_populates="generations",
    )
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="generation",
        cascade="all, delete-orphan",
    )


class DocumentProcessingLease(Base):
    """
    Database-backed distributed lease with monotonic fencing tokens.
    Guarantees that stale workers whose leases expired or were reclaimed
    cannot commit state mutations or overwrite new generations.
    """

    __tablename__ = "document_processing_leases"
    __table_args__ = (
        Index("idx_processing_leases_expiry", "lease_expires_at"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )
    generation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_index_generations.id", ondelete="CASCADE"),
        nullable=True,
    )
    worker_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    fencing_token: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=1,
    )
    lease_acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    lease_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class DocumentChunk(Base):
    """
    Structural document chunk entity with dense vector embedding (384d)
    and PostgreSQL full-text search (tsvector).
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("generation_id", "chunk_index", name="uq_generation_chunk_index"),
        Index("idx_chunks_workspace", "workspace_id"),
        Index("idx_chunks_document", "document_id"),
        Index("idx_chunks_generation", "generation_id"),
        Index("idx_chunks_tsv", "tsv_content", postgresql_using="gin"),
        Index(
            "idx_chunks_embedding_hnsw_384",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    generation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_index_generations.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    page_number: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    section_heading: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )
    token_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    text_content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    tsv_content: Mapped[Any] = mapped_column(
        TSVECTOR().with_variant(Text(), "sqlite"),
        nullable=True,
    )
    model_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="BAAI/bge-small-en-v1.5",
    )
    model_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="5c38ec7",
    )
    embedding: Mapped[List[float]] = mapped_column(
        Vector(384).with_variant(JSON(), "sqlite"),
        nullable=False,
    )

    # Relationships
    generation: Mapped["DocumentIndexGeneration"] = relationship(
        "DocumentIndexGeneration",
        back_populates="chunks",
    )

    @property
    def content(self) -> str:
        return self.text_content


class RagQuery(Base):
    """
    Audit and history entity for RAG queries within workspaces.
    Retained for configured retention period (default 90 days).
    """

    __tablename__ = "rag_queries"
    __table_args__ = (
        Index("idx_rag_queries_workspace_created", "workspace_id", "created_at"),
        Index("idx_rag_queries_user", "user_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    query_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    generated_answer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    retrieval_strategy: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="hybrid_rrf",
    )
    has_unverified_claims: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    execution_time_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    @property
    def answer(self) -> str:
        return self.generated_answer

    @property
    def processing_time_ms(self) -> int:
        return self.execution_time_ms

    @property
    def retrieval_chunks_count(self) -> int:
        return len(self.citations) if self.citations else 0

    def __init__(self, **kwargs):
        if "answer" in kwargs and "generated_answer" not in kwargs:
            kwargs["generated_answer"] = kwargs.pop("answer")
        if "processing_time_ms" in kwargs and "execution_time_ms" not in kwargs:
            kwargs["execution_time_ms"] = kwargs.pop("processing_time_ms")
        if "retrieval_chunks_count" in kwargs:
            kwargs.pop("retrieval_chunks_count")
        super().__init__(**kwargs)

    # Relationships
    citations: Mapped[List["RagQueryCitation"]] = relationship(
        "RagQueryCitation",
        back_populates="query",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class RagQueryCitation(Base):
    """
    Immutable citation snapshot entity.
    Survives retired-generation chunk GC and document deletion,
    preserving full audit trail for the 90-day retention window.
    """

    __tablename__ = "rag_query_citations"
    __table_args__ = (
        Index("idx_rag_citations_query", "query_id"),
        Index("idx_rag_citations_doc", "document_id"),
    )

    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rag_queries.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    generation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
    )
    citation_marker: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    document_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    page_number: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    section_heading: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )
    excerpt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    rank: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    # Relationships
    query: Mapped["RagQuery"] = relationship(
        "RagQuery",
        back_populates="citations",
    )
