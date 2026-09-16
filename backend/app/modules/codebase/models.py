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
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.core.database import Base


class Codebase(Base):
    __tablename__ = "codebases"
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_codebases_id_workspace"),
        UniqueConstraint("workspace_id", "name", name="uq_codebases_name_workspace"),
        CheckConstraint("is_indexed = (active_generation_id IS NOT NULL)", name="ck_codebase_is_indexed_matches_active_gen"),
        Index("idx_codebases_workspace", "workspace_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    repository_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    active_generation_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_indexed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    generations: Mapped[List["CodebaseIndexGeneration"]] = relationship(
        "CodebaseIndexGeneration",
        back_populates="codebase",
        cascade="all, delete-orphan",
        primaryjoin="Codebase.id == CodebaseIndexGeneration.codebase_id",
    )


class CodebaseIndexGeneration(Base):
    __tablename__ = "codebase_index_generations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["codebase_id", "workspace_id"],
            ["codebases.id", "codebases.workspace_id"],
            name="fk_codebase_gen_codebase",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "workspace_id", name="uq_codebase_gen_id_workspace"),
        UniqueConstraint("id", "codebase_id", name="uq_codebase_gen_id_codebase"),
        UniqueConstraint("id", "codebase_id", "workspace_id", name="uq_codebase_gen_id_codebase_ws"),
        UniqueConstraint("codebase_id", "generation_number", name="uq_codebase_gen_num"),
        CheckConstraint("status IN ('building', 'active', 'retired', 'failed')", name="ck_codebase_gen_status"),
        Index("idx_codebase_gen_workspace", "workspace_id"),
        Index("idx_codebase_gen_codebase_status", "codebase_id", "status"),
        Index(
            "uq_codebase_active_generation",
            "codebase_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    codebase_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    generation_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="building")
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1.0")
    embedding_model_revision: Mapped[str] = mapped_column(String(64), nullable=False, default="5c38ec7")
    commit_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_symbols: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    codebase: Mapped["Codebase"] = relationship("Codebase", back_populates="generations", foreign_keys=[codebase_id])
    files: Mapped[List["CodebaseFile"]] = relationship("CodebaseFile", back_populates="generation", cascade="all, delete-orphan")
    chunks: Mapped[List["CodebaseChunk"]] = relationship("CodebaseChunk", back_populates="generation", cascade="all, delete-orphan")


class CodebaseActiveQueryPin(Base):
    __tablename__ = "codebase_active_query_pins"
    __table_args__ = (
        ForeignKeyConstraint(
            ["generation_id", "codebase_id", "workspace_id"],
            ["codebase_index_generations.id", "codebase_index_generations.codebase_id", "codebase_index_generations.workspace_id"],
            name="fk_codebase_query_pins_gen",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("query_id", name="uq_codebase_query_pin_query"),
        Index("idx_codebase_query_pins_gen_expires", "generation_id", "expires_at"),
    )

    generation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    codebase_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CodebaseProcessingLease(Base):
    __tablename__ = "codebase_processing_leases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["generation_id", "codebase_id", "workspace_id"],
            ["codebase_index_generations.id", "codebase_index_generations.codebase_id", "codebase_index_generations.workspace_id"],
            name="fk_codebase_lease_generation",
            ondelete="CASCADE",
        ),
        Index("idx_codebase_leases_expiry", "lease_expires_at"),
    )

    codebase_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=None)
    generation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    worker_id: Mapped[str] = mapped_column(String(255), nullable=False)
    fencing_token: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    lease_acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class CodebaseFile(Base):
    __tablename__ = "codebase_files"
    __table_args__ = (
        ForeignKeyConstraint(
            ["generation_id", "codebase_id", "workspace_id"],
            ["codebase_index_generations.id", "codebase_index_generations.codebase_id", "codebase_index_generations.workspace_id"],
            name="fk_codebase_files_generation",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "generation_id", name="uq_codebase_files_id_gen"),
        UniqueConstraint("generation_id", "file_path", name="uq_codebase_files_path_gen"),
        Index("idx_codebase_files_gen", "generation_id"),
    )

    generation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    codebase_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    language: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    generation: Mapped["CodebaseIndexGeneration"] = relationship("CodebaseIndexGeneration", back_populates="files", foreign_keys=[generation_id])
    symbols: Mapped[List["CodebaseSymbol"]] = relationship("CodebaseSymbol", back_populates="file", cascade="all, delete-orphan", foreign_keys="CodebaseSymbol.file_id")
    chunks: Mapped[List["CodebaseChunk"]] = relationship("CodebaseChunk", back_populates="file", cascade="all, delete-orphan", foreign_keys="CodebaseChunk.file_id")


class CodebaseSymbol(Base):
    __tablename__ = "codebase_symbols"
    __table_args__ = (
        ForeignKeyConstraint(
            ["generation_id", "codebase_id", "workspace_id"],
            ["codebase_index_generations.id", "codebase_index_generations.codebase_id", "codebase_index_generations.workspace_id"],
            name="fk_codebase_symbols_generation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["file_id", "generation_id"],
            ["codebase_files.id", "codebase_files.generation_id"],
            name="fk_codebase_symbols_file",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["parent_symbol_id", "generation_id"],
            ["codebase_symbols.id", "codebase_symbols.generation_id"],
            name="fk_codebase_symbols_parent",
            ondelete="SET NULL",
        ),
        UniqueConstraint("id", "generation_id", name="uq_codebase_symbols_id_gen"),
        CheckConstraint(
            "symbol_type IN ('module', 'class', 'method', 'function', 'interface', 'struct', 'variable', 'type_alias')",
            name="ck_codebase_symbol_type",
        ),
        Index("idx_codebase_symbols_gen_file", "generation_id", "file_id"),
        Index("idx_codebase_symbols_parent", "parent_symbol_id", "generation_id"),
    )

    generation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    codebase_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    symbol_type: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_symbol_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    start_byte: Mapped[int] = mapped_column(Integer, nullable=False)
    end_byte: Mapped[int] = mapped_column(Integer, nullable=False)
    signature: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    docstring: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    file: Mapped["CodebaseFile"] = relationship("CodebaseFile", back_populates="symbols", foreign_keys=[file_id])


class CodebaseRelationship(Base):
    __tablename__ = "codebase_relationships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["generation_id", "codebase_id", "workspace_id"],
            ["codebase_index_generations.id", "codebase_index_generations.codebase_id", "codebase_index_generations.workspace_id"],
            name="fk_codebase_rel_generation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["source_symbol_id", "generation_id"],
            ["codebase_symbols.id", "codebase_symbols.generation_id"],
            name="fk_codebase_rel_source",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["target_symbol_id", "generation_id"],
            ["codebase_symbols.id", "codebase_symbols.generation_id"],
            name="fk_codebase_rel_target",
            ondelete="SET NULL",
        ),
        CheckConstraint(
            "relationship_type IN ('calls', 'imports', 'inherits', 'implements', 'instantiates', 'references')",
            name="ck_codebase_rel_type",
        ),
        CheckConstraint(
            "confidence IN ('syntactic', 'resolved', 'inferred')",
            name="ck_codebase_rel_confidence",
        ),
        Index("idx_codebase_rel_gen", "generation_id"),
        Index("idx_codebase_rel_source", "source_symbol_id", "generation_id"),
        Index("idx_codebase_rel_target", "target_symbol_id", "generation_id"),
    )

    generation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    codebase_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_symbol_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_symbol_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_symbol_name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="resolved")


class CodebaseChunk(Base):
    __tablename__ = "codebase_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["generation_id", "codebase_id", "workspace_id"],
            ["codebase_index_generations.id", "codebase_index_generations.codebase_id", "codebase_index_generations.workspace_id"],
            name="fk_codebase_chunks_generation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["file_id", "generation_id"],
            ["codebase_files.id", "codebase_files.generation_id"],
            name="fk_codebase_chunks_file",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["symbol_id", "generation_id"],
            ["codebase_symbols.id", "codebase_symbols.generation_id"],
            name="fk_codebase_chunks_symbol",
            ondelete="SET NULL",
        ),
        UniqueConstraint("id", "generation_id", name="uq_codebase_chunks_id_gen"),
        UniqueConstraint("file_id", "chunk_index", name="uq_codebase_chunks_file_idx"),
        CheckConstraint(
            "chunk_type IN ('module_header', 'class_definition', 'function_body', 'struct_definition', 'block', 'standalone')",
            name="ck_codebase_chunk_type",
        ),
        Index("idx_codebase_chunks_gen_codebase", "generation_id", "codebase_id"),
        Index("idx_codebase_chunks_symbol", "symbol_id", "generation_id"),
    )

    generation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    symbol_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    codebase_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    language: Mapped[str] = mapped_column(String(64), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(384), nullable=False)

    generation: Mapped["CodebaseIndexGeneration"] = relationship("CodebaseIndexGeneration", back_populates="chunks", foreign_keys=[generation_id])
    file: Mapped["CodebaseFile"] = relationship("CodebaseFile", back_populates="chunks", foreign_keys=[file_id])


class CodebaseQuery(Base):
    __tablename__ = "codebase_queries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["codebase_id", "workspace_id"],
            ["codebases.id", "codebases.workspace_id"],
            name="fk_codebase_queries_codebase",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "workspace_id", name="uq_codebase_queries_id_ws"),
        Index("idx_codebase_queries_ws", "workspace_id", "codebase_id"),
    )

    codebase_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    generation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    generation_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)
    embedding_model_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    total_chunks_retrieved: Mapped[int] = mapped_column(Integer, nullable=False)
    rerank_top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    citations: Mapped[List["CodebaseQueryCitation"]] = relationship("CodebaseQueryCitation", back_populates="query", cascade="all, delete-orphan")


class CodebaseQueryCitation(Base):
    __tablename__ = "codebase_query_citations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["query_id", "workspace_id"],
            ["codebase_queries.id", "codebase_queries.workspace_id"],
            name="fk_codebase_citations_query",
            ondelete="CASCADE",
        ),
        Index("idx_codebase_citations_query", "query_id"),
    )

    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    generation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    generation_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    snippet_preview: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    query: Mapped["CodebaseQuery"] = relationship("CodebaseQuery", back_populates="citations")
