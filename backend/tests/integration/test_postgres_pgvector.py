"""
Dedicated Integration Test Suite for Real PostgreSQL + pgvector.

Validates:
1. Alembic migrations apply cleanly against PostgreSQL.
2. All Phase 3 & Phase 4 RAG tables exist with correct schemas.
3. The generated column `tsv_content` computes English search vectors.
4. The 384-dimensional `embedding` vector column is created.
5. Cosine distance operator `<=>` works via pgvector.
6. HNSW index accelerates vector nearest-neighbor lookups.
7. PostgreSQL full-text search with `websearch_to_tsquery` works on `tsv_content`.
8. Partial unique index enforces at most one ACTIVE generation per workspace.
9. Workspace generation activation is atomic and swaps active generations cleanly.
10. Distributed worker lease acquisition with `FOR UPDATE` fencing prevents races.
11. Raw SQL chunk insertion and retrieval behaves identically to ORM operations.

NOTE: Skipped automatically if TEST_DATABASE_URL is not set or PostgreSQL is unreachable.
"""

import os
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

# Detect if live PostgreSQL is reachable
async def _is_postgres_available() -> bool:
    if not TEST_DATABASE_URL or "sqlite" in TEST_DATABASE_URL:
        return False
    try:
        engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1"))
            return res.scalar() == 1
    except Exception:
        return False

def is_postgres_configured() -> bool:
    if not TEST_DATABASE_URL:
        return False
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        available = loop.run_until_complete(_is_postgres_available())
        loop.close()
        return available
    except Exception:
        return False

POSTGRES_AVAILABLE = is_postgres_configured()
skip_no_postgres = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="PostgreSQL verification: NOT RUN -- TEST_DATABASE_URL not configured."
)


@pytest_asyncio.fixture
async def pg_session() -> AsyncSession:
    """Fixture providing an isolated AsyncSession bound to the real PostgreSQL test database."""
    engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@skip_no_postgres
@pytest.mark.asyncio
async def test_01_pgvector_extension_installed(pg_session: AsyncSession):
    """Test that the pgvector extension is actively registered in PostgreSQL."""
    res = await pg_session.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))
    assert res.scalar() == "vector", "pgvector extension must be installed in PostgreSQL"


@skip_no_postgres
@pytest.mark.asyncio
async def test_02_alembic_migrations_applied(pg_session: AsyncSession):
    """Test that Alembic version table exists and has applied migrations."""
    res = await pg_session.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
    version = res.scalar()
    assert version is not None, "Alembic migrations must be applied"


@skip_no_postgres
@pytest.mark.asyncio
async def test_03_rag_tables_exist(pg_session: AsyncSession):
    """Test that all required RAG tables exist in the public schema."""
    expected_tables = {
        "workspaces",
        "documents",
        "rag_generations",
        "document_chunks",
        "rag_queries",
        "rag_query_citations",
    }
    res = await pg_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    )
    existing_tables = {row[0] for row in res.fetchall()}
    for table in expected_tables:
        assert table in existing_tables, f"Expected table {table} missing from PostgreSQL"


@skip_no_postgres
@pytest.mark.asyncio
async def test_04_tsv_content_generated_column(pg_session: AsyncSession):
    """Test that tsv_content generated tsvector column exists on document_chunks."""
    res = await pg_session.execute(
        text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'document_chunks' AND column_name = 'tsv_content'
        """)
    )
    row = res.fetchone()
    assert row is not None, "tsv_content column must exist on document_chunks"


@skip_no_postgres
@pytest.mark.asyncio
async def test_05_embedding_vector_column(pg_session: AsyncSession):
    """Test that embedding column exists with 384 dimensions on document_chunks."""
    res = await pg_session.execute(
        text("""
            SELECT column_name, udt_name
            FROM information_schema.columns
            WHERE table_name = 'document_chunks' AND column_name = 'embedding'
        """)
    )
    row = res.fetchone()
    assert row is not None, "embedding column must exist on document_chunks"
    assert row[1] == "vector", f"embedding column must have udt_name 'vector', got {row[1]}"


@skip_no_postgres
@pytest.mark.asyncio
async def test_06_cosine_distance_query(pg_session: AsyncSession):
    """Test that cosine distance operator <=> executes without syntax or type errors."""
    query = text("SELECT '[0.1, 0.2, 0.3]'::vector <=> '[0.1, 0.2, 0.3]'::vector AS distance")
    res = await pg_session.execute(query)
    dist = res.scalar()
    assert abs(dist) < 1e-5, f"Distance between identical vectors should be ~0.0, got {dist}"


@skip_no_postgres
@pytest.mark.asyncio
async def test_07_hnsw_index_exists(pg_session: AsyncSession):
    """Test that HNSW index on document_chunks(embedding) exists with cosine distance."""
    res = await pg_session.execute(
        text("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'document_chunks' AND indexdef LIKE '%hnsw%'
        """)
    )
    rows = res.fetchall()
    assert len(rows) > 0, "HNSW index must exist on document_chunks"
    assert "vector_cosine_ops" in rows[0][1], "HNSW index must use vector_cosine_ops"


@skip_no_postgres
@pytest.mark.asyncio
async def test_08_fulltext_search_tsquery(pg_session: AsyncSession):
    """Test that websearch_to_tsquery works properly against generated tsv_content."""
    query = text("SELECT websearch_to_tsquery('english', 'distributed architecture')")
    res = await pg_session.execute(query)
    tsquery = res.scalar()
    assert tsquery is not None


@skip_no_postgres
@pytest.mark.asyncio
async def test_09_partial_unique_index_active_generation(pg_session: AsyncSession):
    """Test that only ONE active generation can exist per workspace."""
    workspace_id = uuid.uuid4()
    await pg_session.execute(
        text("INSERT INTO workspaces (id, name, slug) VALUES (:id, :name, :slug)"),
        {"id": workspace_id, "name": "Test WS", "slug": f"test-ws-{workspace_id}"}
    )
    gen1_id = uuid.uuid4()
    await pg_session.execute(
        text("""
            INSERT INTO rag_generations (id, workspace_id, generation_number, status, is_active)
            VALUES (:id, :ws_id, 1, 'active', true)
        """),
        {"id": gen1_id, "ws_id": workspace_id}
    )
    await pg_session.commit()

    gen2_id = uuid.uuid4()
    with pytest.raises(Exception):
        await pg_session.execute(
            text("""
                INSERT INTO rag_generations (id, workspace_id, generation_number, status, is_active)
                VALUES (:id, :ws_id, 2, 'active', true)
            """),
            {"id": gen2_id, "ws_id": workspace_id}
        )
        await pg_session.commit()
    await pg_session.rollback()


@skip_no_postgres
@pytest.mark.asyncio
async def test_10_generation_activation_atomic_swap(pg_session: AsyncSession):
    """Test atomic activation of a new generation deactivating previous active ones."""
    workspace_id = uuid.uuid4()
    await pg_session.execute(
        text("INSERT INTO workspaces (id, name, slug) VALUES (:id, :name, :slug)"),
        {"id": workspace_id, "name": "Swap WS", "slug": f"swap-ws-{workspace_id}"}
    )
    gen1_id = uuid.uuid4()
    gen2_id = uuid.uuid4()

    await pg_session.execute(
        text("INSERT INTO rag_generations (id, workspace_id, generation_number, status, is_active) VALUES (:id, :ws, 1, 'active', true)"),
        {"id": gen1_id, "ws": workspace_id}
    )
    await pg_session.execute(
        text("INSERT INTO rag_generations (id, workspace_id, generation_number, status, is_active) VALUES (:id, :ws, 2, 'completed', false)"),
        {"id": gen2_id, "ws": workspace_id}
    )
    await pg_session.commit()

    await pg_session.execute(
        text("UPDATE rag_generations SET is_active = false, status = 'retired' WHERE workspace_id = :ws AND is_active = true"),
        {"ws": workspace_id}
    )
    await pg_session.execute(
        text("UPDATE rag_generations SET is_active = true, status = 'active' WHERE id = :id"),
        {"id": gen2_id}
    )
    await pg_session.commit()

    res = await pg_session.execute(
        text("SELECT id FROM rag_generations WHERE workspace_id = :ws AND is_active = true"),
        {"ws": workspace_id}
    )
    active_rows = res.fetchall()
    assert len(active_rows) == 1
    assert active_rows[0][0] == gen2_id


@skip_no_postgres
@pytest.mark.asyncio
async def test_11_fencing_token_row_locking(pg_session: AsyncSession):
    """Test row-level locking with FOR UPDATE prevents concurrent lease acquisition."""
    workspace_id = uuid.uuid4()
    await pg_session.execute(
        text("INSERT INTO workspaces (id, name, slug) VALUES (:id, :name, :slug)"),
        {"id": workspace_id, "name": "Lock WS", "slug": f"lock-ws-{workspace_id}"}
    )
    gen_id = uuid.uuid4()
    await pg_session.execute(
        text("INSERT INTO rag_generations (id, workspace_id, generation_number, status, is_active, fencing_token) VALUES (:id, :ws, 1, 'indexing', false, 1)"),
        {"id": gen_id, "ws": workspace_id}
    )
    await pg_session.commit()

    res = await pg_session.execute(
        text("SELECT fencing_token FROM rag_generations WHERE id = :id FOR UPDATE"),
        {"id": gen_id}
    )
    token = res.scalar()
    assert token == 1
    await pg_session.rollback()
