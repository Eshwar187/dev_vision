"""
Dedicated Integration Test Suite for Real PostgreSQL Concurrency & Active Query Pinning.
Authoritative target: Supabase PostgreSQL.

Validates:
1. Active query pin foreign key constraint ON DELETE RESTRICT prevents generation deletion at the DB level.
2. Garbage collection SELECT ... FOR UPDATE SKIP LOCKED prevents race conditions between concurrent GC workers.
3. Partial unique index on codebase_index_generations enforces at most one ACTIVE generation per codebase.
4. Schema isolation: runs tests in an ephemeral dedicated schema, never touching public or production tables.

NOTE: Skipped cleanly if TEST_DATABASE_URL is not set.
Reporting guarantee: "PostgreSQL verification: NOT RUN — TEST_DATABASE_URL not configured."
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from sqlalchemy import text, select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.database import Base
from app.modules.codebase.models import (
    Codebase,
    CodebaseActiveQueryPin,
    CodebaseIndexGeneration,
)
from app.modules.workspaces.models import Workspace

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


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
async def pg_isolated_engine():
    """Provides a PostgreSQL engine and creates/tears down an ephemeral schema."""
    if not POSTGRES_AVAILABLE:
        pytest.skip("PostgreSQL verification: NOT RUN -- TEST_DATABASE_URL not configured.")

    schema_name = f"test_conc_{uuid.uuid4().hex[:8]}"
    engine = create_async_engine(
        TEST_DATABASE_URL,
        pool_pre_ping=True,
        execution_options={"schema_translate_map": {None: schema_name}},
    )

    # Setup ephemeral schema and tables
    admin_engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    async with admin_engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
        await conn.execute(text(f"SET search_path TO {schema_name}, public"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine, schema_name

    # Teardown ephemeral schema
    async with admin_engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
    await admin_engine.dispose()
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_isolated_engine) -> AsyncSession:
    """Fixture providing an AsyncSession bound to the isolated ephemeral schema."""
    engine, _ = pg_isolated_engine
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@skip_no_postgres
@pytest.mark.asyncio
async def test_pg_pin_fk_on_delete_restrict(pg_session: AsyncSession):
    """
    Test PostgreSQL ON DELETE RESTRICT constraint.
    An active query pin referencing a generation prevents deletion of that generation.
    """
    ws = Workspace(id=uuid.uuid4(), name="PG Pin WS", slug=f"pg-ws-{uuid.uuid4().hex[:6]}")
    pg_session.add(ws)
    await pg_session.flush()

    cb = Codebase(id=uuid.uuid4(), workspace_id=ws.id, name="PG-Pin-Repo", is_indexed=False)
    pg_session.add(cb)
    await pg_session.flush()

    gen = CodebaseIndexGeneration(
        id=uuid.uuid4(),
        codebase_id=cb.id,
        workspace_id=ws.id,
        generation_number=1,
        status="retired",
        retired_at=datetime.now(timezone.utc) - timedelta(hours=25),
    )
    pg_session.add(gen)
    await pg_session.flush()

    # Create active query pin
    pin = CodebaseActiveQueryPin(
        query_id=uuid.uuid4(),
        generation_id=gen.id,
        codebase_id=cb.id,
        workspace_id=ws.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    pg_session.add(pin)
    await pg_session.commit()

    # Attempt to delete generation while pinned
    del_stmt = delete(CodebaseIndexGeneration).where(CodebaseIndexGeneration.id == gen.id)
    with pytest.raises(IntegrityError):
        await pg_session.execute(del_stmt)
        await pg_session.commit()
    await pg_session.rollback()


@skip_no_postgres
@pytest.mark.asyncio
async def test_pg_gc_for_update_skip_locked_concurrent_workers(pg_isolated_engine):
    """
    Test PostgreSQL FOR UPDATE SKIP LOCKED behavior with concurrent GC workers.
    Worker 1 locks candidate generation rows; Worker 2 skips locked rows without blocking.
    """
    engine, _ = pg_isolated_engine
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    ws_id = uuid.uuid4()
    cb_id = uuid.uuid4()
    gen1_id = uuid.uuid4()
    gen2_id = uuid.uuid4()

    # Seed 2 retired generations
    async with session_factory() as session:
        ws = Workspace(id=ws_id, name="PG GC WS", slug=f"pg-gc-{uuid.uuid4().hex[:6]}")
        session.add(ws)
        cb = Codebase(id=cb_id, workspace_id=ws_id, name="PG-GC-Repo", is_indexed=False)
        session.add(cb)
        await session.flush()

        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        g1 = CodebaseIndexGeneration(id=gen1_id, codebase_id=cb_id, workspace_id=ws_id, generation_number=1, status="retired", retired_at=old_time)
        g2 = CodebaseIndexGeneration(id=gen2_id, codebase_id=cb_id, workspace_id=ws_id, generation_number=2, status="retired", retired_at=old_time)
        session.add_all([g1, g2])
        await session.commit()

    # Worker 1 acquires lock on candidate 1
    session1 = session_factory()
    session2 = session_factory()

    try:
        # Worker 1 selects with FOR UPDATE SKIP LOCKED limit 1
        stmt1 = (
            select(CodebaseIndexGeneration.id)
            .where(
                CodebaseIndexGeneration.codebase_id == cb_id,
                CodebaseIndexGeneration.status == "retired",
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        res1 = await session1.execute(stmt1)
        locked_by_w1 = res1.scalars().all()
        assert len(locked_by_w1) == 1
        locked_id = locked_by_w1[0]

        # Worker 2 concurrently selects with FOR UPDATE SKIP LOCKED
        stmt2 = (
            select(CodebaseIndexGeneration.id)
            .where(
                CodebaseIndexGeneration.codebase_id == cb_id,
                CodebaseIndexGeneration.status == "retired",
            )
            .with_for_update(skip_locked=True)
        )
        res2 = await session2.execute(stmt2)
        available_for_w2 = res2.scalars().all()

        # Worker 2 must NOT receive the row locked by Worker 1
        assert locked_id not in available_for_w2
        assert len(available_for_w2) == 1

        # Worker 1 deletes its locked row and commits
        await session1.execute(delete(CodebaseIndexGeneration).where(CodebaseIndexGeneration.id == locked_id))
        await session1.commit()

        # Worker 2 deletes its row and commits
        await session2.execute(delete(CodebaseIndexGeneration).where(CodebaseIndexGeneration.id.in_(available_for_w2)))
        await session2.commit()

    finally:
        await session1.close()
        await session2.close()


@skip_no_postgres
@pytest.mark.asyncio
async def test_pg_active_generation_partial_unique_index(pg_session: AsyncSession):
    """
    Test PostgreSQL partial unique index on codebase_index_generations (WHERE status = 'active').
    Prevents multiple active generations for the same codebase.
    """
    ws = Workspace(id=uuid.uuid4(), name="PG Unique WS", slug=f"pg-uq-{uuid.uuid4().hex[:6]}")
    pg_session.add(ws)
    await pg_session.flush()

    cb = Codebase(id=uuid.uuid4(), workspace_id=ws.id, name="PG-Unique-Repo", is_indexed=False)
    pg_session.add(cb)
    await pg_session.flush()

    gen1 = CodebaseIndexGeneration(
        id=uuid.uuid4(),
        codebase_id=cb.id,
        workspace_id=ws.id,
        generation_number=1,
        status="active",
        activated_at=datetime.now(timezone.utc),
    )
    pg_session.add(gen1)
    await pg_session.commit()

    gen2 = CodebaseIndexGeneration(
        id=uuid.uuid4(),
        codebase_id=cb.id,
        workspace_id=ws.id,
        generation_number=2,
        status="active",
        activated_at=datetime.now(timezone.utc),
    )
    pg_session.add(gen2)
    with pytest.raises(IntegrityError):
        await pg_session.commit()
    await pg_session.rollback()
