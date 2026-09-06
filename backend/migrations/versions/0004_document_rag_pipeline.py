"""Document RAG pipeline schema

Revision ID: 0004_document_rag_pipeline
Revises: 0003_document_management
Create Date: 2026-09-06 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0004_document_rag_pipeline"
down_revision: Union[str, None] = "0003_document_management"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. document_index_generations
    op.create_table(
        "document_index_generations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("generation_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="building", nullable=False),
        sa.Column("stage", sa.String(length=32), server_default="extracting", nullable=False),
        sa.Column("pipeline_version", sa.String(length=32), server_default="v1.0", nullable=False),
        sa.Column("chunking_strategy", sa.String(length=64), server_default="recursive_structural", nullable=False),
        sa.Column("chunk_size", sa.Integer(), server_default="500", nullable=False),
        sa.Column("chunk_overlap", sa.Integer(), server_default="50", nullable=False),
        sa.Column("tokenizer_name", sa.String(length=128), server_default="BAAI/bge-small-en-v1.5", nullable=False),
        sa.Column("total_chunks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unextractable_pages", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("document_id", "generation_number", name="uq_doc_generation"),
    )
    op.create_index("idx_doc_index_gen_workspace", "document_index_generations", ["workspace_id"], unique=False)
    op.create_index("idx_doc_index_gen_status", "document_index_generations", ["document_id", "status"], unique=False)
    op.create_index(
        "uq_doc_single_active_gen",
        "document_index_generations",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    # 2. document_processing_leases
    op.create_table(
        "document_processing_leases",
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "generation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_index_generations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("worker_id", sa.String(length=128), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column("lease_acquired_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_processing_leases_expiry", "document_processing_leases", ["lease_expires_at"], unique=False)

    # 3. document_chunks
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "generation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_index_generations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_heading", sa.String(length=512), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column(
            "tsv_content",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', text_content)", persisted=True),
            nullable=True,
        ),
        sa.Column("model_name", sa.String(length=128), server_default="BAAI/bge-small-en-v1.5", nullable=False),
        sa.Column("model_version", sa.String(length=64), server_default="5c38ec7", nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("generation_id", "chunk_index", name="uq_generation_chunk_index"),
    )
    op.create_index("idx_chunks_workspace", "document_chunks", ["workspace_id"], unique=False)
    op.create_index("idx_chunks_document", "document_chunks", ["document_id"], unique=False)
    op.create_index("idx_chunks_generation", "document_chunks", ["generation_id"], unique=False)
    op.create_index("idx_chunks_tsv", "document_chunks", ["tsv_content"], unique=False, postgresql_using="gin")
    op.create_index(
        "idx_chunks_embedding_hnsw_384",
        "document_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # 4. Alter documents table: add active_generation_id
    op.add_column(
        "documents",
        sa.Column(
            "active_generation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_index_generations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 5. rag_queries
    op.create_table(
        "rag_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("generated_answer", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("retrieval_strategy", sa.String(length=64), server_default="hybrid_rrf", nullable=False),
        sa.Column("has_unverified_claims", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("execution_time_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_rag_queries_workspace_created", "rag_queries", ["workspace_id", "created_at"], unique=False)
    op.create_index("idx_rag_queries_user", "rag_queries", ["user_id"], unique=False)

    # 6. rag_query_citations (immutable historical snapshot)
    op.create_table(
        "rag_query_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "query_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rag_queries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_chunks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("citation_marker", sa.String(length=16), nullable=False),
        sa.Column("document_name", sa.String(length=255), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_heading", sa.String(length=512), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_rag_citations_query", "rag_query_citations", ["query_id"], unique=False)
    op.create_index("idx_rag_citations_doc", "rag_query_citations", ["document_id"], unique=False)


def downgrade() -> None:
    op.drop_table("rag_query_citations")
    op.drop_table("rag_queries")
    op.drop_column("documents", "active_generation_id")
    op.drop_table("document_chunks")
    op.drop_table("document_processing_leases")
    op.drop_table("document_index_generations")
