\"\"\"Codebase Intelligence & Code RAG Schema

Revision ID: 0005_codebase_rag_schema
Revises: 0004_document_rag_pipeline
Create Date: 2026-09-16 00:00:00.000000

\"\"\"
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0005_codebase_rag_schema"
down_revision: Union[str, None] = "0004_document_rag_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure pg_trgm and vector exist if not already
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    # 1. codebases
    op.create_table(
        "codebases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("repository_url", sa.String(length=1024), nullable=True),
        sa.Column("default_branch", sa.String(length=255), server_default="main", nullable=False),
        sa.Column("active_generation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_indexed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("id", "workspace_id", name="uq_codebases_id_workspace"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_codebases_name_workspace"),
        sa.CheckConstraint(
            "is_indexed = (active_generation_id IS NOT NULL)",
            name="ck_codebase_is_indexed_matches_active_gen",
        ),
    )
    op.create_index("idx_codebases_workspace", "codebases", ["workspace_id"], unique=False)

    # 2. codebase_index_generations
    op.create_table(
        "codebase_index_generations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "codebase_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("generation_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="building", nullable=False),
        sa.Column("pipeline_version", sa.String(length=32), server_default="v1.0", nullable=False),
        sa.Column("embedding_model_revision", sa.String(length=64), server_default="5c38ec7", nullable=False),
        sa.Column("commit_hash", sa.String(length=64), nullable=True),
        sa.Column("branch", sa.String(length=255), nullable=True),
        sa.Column("total_files", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_symbols", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_chunks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["codebase_id", "workspace_id"],
            ["codebases.id", "codebases.workspace_id"],
            name="fk_codebase_gen_codebase",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "workspace_id", name="uq_codebase_gen_id_workspace"),
        sa.UniqueConstraint("id", "codebase_id", name="uq_codebase_gen_id_codebase"),
        sa.UniqueConstraint("id", "codebase_id", "workspace_id", name="uq_codebase_gen_id_codebase_ws"),
        sa.UniqueConstraint("codebase_id", "generation_number", name="uq_codebase_gen_num"),
        sa.CheckConstraint(
            "status IN ('building', 'active', 'retired', 'failed')",
            name="ck_codebase_gen_status",
        ),
    )
    op.create_index("idx_codebase_gen_workspace", "codebase_index_generations", ["workspace_id"], unique=False)
    op.create_index("idx_codebase_gen_codebase_status", "codebase_index_generations", ["codebase_id", "status"], unique=False)
    op.create_index(
        "uq_codebase_active_generation",
        "codebase_index_generations",
        ["codebase_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    # Circular FK on codebases for active_generation_id
    op.create_foreign_key(
        "fk_codebases_active_generation",
        "codebases",
        "codebase_index_generations",
        ["active_generation_id", "id"],
        ["id", "codebase_id"],
        ondelete="SET NULL",
    )

    # 3. codebase_active_query_pins (ON DELETE RESTRICT - Hard Requirement)
    op.create_table(
        "codebase_active_query_pins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("codebase_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["generation_id", "codebase_id", "workspace_id"],
            ["codebase_index_generations.id", "codebase_index_generations.codebase_id", "codebase_index_generations.workspace_id"],
            name="fk_codebase_query_pins_gen",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("query_id", name="uq_codebase_query_pin_query"),
    )
    op.create_index(
        "idx_codebase_query_pins_gen_expires",
        "codebase_active_query_pins",
        ["generation_id", "expires_at"],
        unique=False,
    )

    # 4. codebase_processing_leases
    op.create_table(
        "codebase_processing_leases",
        sa.Column("codebase_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", sa.String(length=255), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column("lease_acquired_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["generation_id", "codebase_id", "workspace_id"],
            ["codebase_index_generations.id", "codebase_index_generations.codebase_id", "codebase_index_generations.workspace_id"],
            name="fk_codebase_lease_generation",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_codebase_leases_expiry", "codebase_processing_leases", ["lease_expires_at"], unique=False)

    # 5. codebase_files
    op.create_table(
        "codebase_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("codebase_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("language", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["generation_id", "codebase_id", "workspace_id"],
            ["codebase_index_generations.id", "codebase_index_generations.codebase_id", "codebase_index_generations.workspace_id"],
            name="fk_codebase_files_generation",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "generation_id", name="uq_codebase_files_id_gen"),
        sa.UniqueConstraint("generation_id", "file_path", name="uq_codebase_files_path_gen"),
    )
    op.create_index("idx_codebase_files_gen", "codebase_files", ["generation_id"], unique=False)
    op.create_index("idx_codebase_files_path_trgm", "codebase_files", ["file_path"], unique=False, postgresql_using="gin", postgresql_ops={"file_path": "gin_trgm_ops"})

    # 6. codebase_symbols
    op.create_table(
        "codebase_symbols",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("codebase_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("symbol_type", sa.String(length=64), nullable=False),
        sa.Column("parent_symbol_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("start_byte", sa.Integer(), nullable=False),
        sa.Column("end_byte", sa.Integer(), nullable=False),
        sa.Column("signature", sa.String(length=1024), nullable=True),
        sa.Column("docstring", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["generation_id", "codebase_id", "workspace_id"],
            ["codebase_index_generations.id", "codebase_index_generations.codebase_id", "codebase_index_generations.workspace_id"],
            name="fk_codebase_symbols_generation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id", "generation_id"],
            ["codebase_files.id", "codebase_files.generation_id"],
            name="fk_codebase_symbols_file",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "generation_id", name="uq_codebase_symbols_id_gen"),
        sa.CheckConstraint(
            "symbol_type IN ('module', 'class', 'method', 'function', 'interface', 'struct', 'variable', 'type_alias')",
            name="ck_codebase_symbol_type",
        ),
    )
    # Self-referential parent_symbol_id FK within same generation
    op.create_foreign_key(
        "fk_codebase_symbols_parent",
        "codebase_symbols",
        "codebase_symbols",
        ["parent_symbol_id", "generation_id"],
        ["id", "generation_id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_codebase_symbols_gen_file", "codebase_symbols", ["generation_id", "file_id"], unique=False)
    op.create_index("idx_codebase_symbols_parent", "codebase_symbols", ["parent_symbol_id", "generation_id"], unique=False)
    op.create_index("idx_codebase_symbols_name_trgm", "codebase_symbols", ["name"], unique=False, postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"})

    # 7. codebase_relationships
    op.create_table(
        "codebase_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("codebase_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_symbol_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_symbol_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("relationship_type", sa.String(length=32), nullable=False),
        sa.Column("target_symbol_name", sa.String(length=255), nullable=False),
        sa.Column("target_file_path", sa.String(length=1024), nullable=True),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.String(length=16), server_default="resolved", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["generation_id", "codebase_id", "workspace_id"],
            ["codebase_index_generations.id", "codebase_index_generations.codebase_id", "codebase_index_generations.workspace_id"],
            name="fk_codebase_rel_generation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_symbol_id", "generation_id"],
            ["codebase_symbols.id", "codebase_symbols.generation_id"],
            name="fk_codebase_rel_source",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_symbol_id", "generation_id"],
            ["codebase_symbols.id", "codebase_symbols.generation_id"],
            name="fk_codebase_rel_target",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "relationship_type IN ('calls', 'imports', 'inherits', 'implements', 'instantiates', 'references')",
            name="ck_codebase_rel_type",
        ),
        sa.CheckConstraint(
            "confidence IN ('syntactic', 'resolved', 'inferred')",
            name="ck_codebase_rel_confidence",
        ),
    )
    op.create_index("idx_codebase_rel_gen", "codebase_relationships", ["generation_id"], unique=False)
    op.create_index("idx_codebase_rel_source", "codebase_relationships", ["source_symbol_id", "generation_id"], unique=False)
    op.create_index("idx_codebase_rel_target", "codebase_relationships", ["target_symbol_id", "generation_id"], unique=False)

    # 8. codebase_chunks
    op.create_table(
        "codebase_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("codebase_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("language", sa.String(length=64), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("chunk_type", sa.String(length=32), nullable=False),
        sa.Column("scope_path", sa.String(length=512), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                \"setweight(to_tsvector('simple', coalesce(file_path, '')), 'A') || \"
                \"setweight(to_tsvector('simple', coalesce(scope_path, '')), 'B') || \"
                \"setweight(to_tsvector('simple', content), 'C')\",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["generation_id", "codebase_id", "workspace_id"],
            ["codebase_index_generations.id", "codebase_index_generations.codebase_id", "codebase_index_generations.workspace_id"],
            name="fk_codebase_chunks_generation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id", "generation_id"],
            ["codebase_files.id", "codebase_files.generation_id"],
            name="fk_codebase_chunks_file",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["symbol_id", "generation_id"],
            ["codebase_symbols.id", "codebase_symbols.generation_id"],
            name="fk_codebase_chunks_symbol",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("id", "generation_id", name="uq_codebase_chunks_id_gen"),
        sa.UniqueConstraint("file_id", "chunk_index", name="uq_codebase_chunks_file_idx"),
        sa.CheckConstraint(
            "chunk_type IN ('module_header', 'class_definition', 'function_body', 'struct_definition', 'block', 'standalone')",
            name="ck_codebase_chunk_type",
        ),
    )
    op.create_index("idx_codebase_chunks_gen_codebase", "codebase_chunks", ["generation_id", "codebase_id"], unique=False)
    op.create_index("idx_codebase_chunks_symbol", "codebase_chunks", ["symbol_id", "generation_id"], unique=False)
    op.create_index("idx_codebase_chunks_tsv", "codebase_chunks", ["tsv"], unique=False, postgresql_using="gin")
    op.create_index("idx_codebase_chunks_path_trgm", "codebase_chunks", ["file_path"], unique=False, postgresql_using="gin", postgresql_ops={"file_path": "gin_trgm_ops"})
    op.create_index("idx_codebase_chunks_scope_trgm", "codebase_chunks", ["scope_path"], unique=False, postgresql_using="gin", postgresql_ops={"scope_path": "gin_trgm_ops"})
    op.create_index(
        "idx_codebase_chunks_embedding_hnsw",
        "codebase_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # 9. codebase_queries (Historical Audit Log - NO blocking FK to generations/chunks)
    op.create_table(
        "codebase_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("codebase_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_number", sa.Integer(), nullable=False),
        sa.Column("pipeline_version", sa.String(length=32), nullable=False),
        sa.Column("embedding_model_revision", sa.String(length=64), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("retrieval_strategy", sa.String(length=32), nullable=False),
        sa.Column("total_chunks_retrieved", sa.Integer(), nullable=False),
        sa.Column("rerank_top_k", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["codebase_id", "workspace_id"],
            ["codebases.id", "codebases.workspace_id"],
            name="fk_codebase_queries_codebase",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "workspace_id", name="uq_codebase_queries_id_ws"),
    )
    op.create_index("idx_codebase_queries_ws", "codebase_queries", ["workspace_id", "codebase_id"], unique=False)

    # 10. codebase_query_citations (Historical Evidence Log - NO FK to codebase_chunks)
    op.create_table(
        "codebase_query_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_number", sa.Integer(), nullable=False),
        sa.Column("pipeline_version", sa.String(length=32), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("snippet_preview", sa.Text(), nullable=False),
        sa.Column("chunk_content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["query_id", "workspace_id"],
            ["codebase_queries.id", "codebase_queries.workspace_id"],
            name="fk_codebase_citations_query",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_codebase_citations_query", "codebase_query_citations", ["query_id"], unique=False)


def downgrade() -> None:
    op.drop_table("codebase_query_citations")
    op.drop_table("codebase_queries")
    op.drop_table("codebase_chunks")
    op.drop_table("codebase_relationships")
    op.drop_table("codebase_symbols")
    op.drop_table("codebase_files")
    op.drop_table("codebase_processing_leases")
    op.drop_table("codebase_active_query_pins")
    op.drop_constraint("fk_codebases_active_generation", "codebases", type_="foreignkey")
    op.drop_table("codebase_index_generations")
    op.drop_table("codebases")
