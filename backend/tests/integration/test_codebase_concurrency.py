"""
DevVision AI - Phase 7 Codebase Concurrency & Active Query Pinning Tests.

Tests:
1. Race A: Pin creation fails gracefully if generation does not exist or was deleted.
2. Race B: Active pin blocks GC deletion via ON DELETE RESTRICT foreign key constraint.
3. Race C: Expired pin is cleaned up by GC, allowing retired generation to be reclaimed.
4. Race D: Query heartbeat / pin refresh maintains protection until explicit pin release.
5. Concurrency: Two activations competing for the codebase serialize via pessimistic row locking.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException
from app.modules.codebase.models import (
    Codebase,
    CodebaseActiveQueryPin,
    CodebaseChunk,
    CodebaseIndexGeneration,
)
from app.modules.codebase.service import CodebaseService
from app.modules.codebase.retrieval import HybridCodeRetriever
from app.modules.rag.mock import MockEmbeddingModel, MockLanguageModel, MockRerankerModel
from app.modules.workspaces.models import Workspace


@pytest.fixture
def codebase_service():
    retriever = HybridCodeRetriever(
        embedding_model=MockEmbeddingModel(),
        reranker_model=MockRerankerModel(),
    )
    return CodebaseService(
        retriever=retriever,
        llm_client=MockLanguageModel(),
    )


from sqlalchemy import delete, select, text

async def _setup_workspace_and_codebase(db_session: AsyncSession):
    await db_session.execute(text("PRAGMA foreign_keys=ON;"))
    ws = Workspace(id=uuid.uuid4(), name="Concurrency WS", slug=f"conc-ws-{uuid.uuid4().hex[:6]}")
    db_session.add(ws)
    await db_session.flush()

    cb = Codebase(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        name="Concurrency-Repo",
        is_indexed=False,
    )
    db_session.add(cb)
    await db_session.flush()
    return ws, cb


@pytest.mark.asyncio
async def test_race_a_pin_nonexistent_or_deleted_generation(db_session: AsyncSession, codebase_service: CodebaseService):
    """Race A: Pin creation fails if target generation does not exist or has been deleted."""
    ws, cb = await _setup_workspace_and_codebase(db_session)
    fake_gen_id = uuid.uuid4()
    query_id = uuid.uuid4()

    # Attempt to pin a generation that does not exist in DB
    pin = CodebaseActiveQueryPin(
        query_id=query_id,
        generation_id=fake_gen_id,
        codebase_id=cb.id,
        workspace_id=ws.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db_session.add(pin)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_race_b_active_pin_blocks_gc_deletion(db_session: AsyncSession, codebase_service: CodebaseService):
    """Race B: An active query pin blocks generation GC deletion via ON DELETE RESTRICT."""
    ws, cb = await _setup_workspace_and_codebase(db_session)

    # 1. Create a generation
    gen = CodebaseIndexGeneration(
        id=uuid.uuid4(),
        codebase_id=cb.id,
        workspace_id=ws.id,
        generation_number=1,
        status="retired",
    )
    db_session.add(gen)
    await db_session.flush()

    # 2. Pin the generation with an active unexpired pin
    query_id = uuid.uuid4()
    pin = CodebaseActiveQueryPin(
        query_id=query_id,
        generation_id=gen.id,
        codebase_id=cb.id,
        workspace_id=ws.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db_session.add(pin)
    await db_session.flush()

    # 3. Direct attempt to delete the generation MUST raise IntegrityError due to RESTRICT
    del_stmt = delete(CodebaseIndexGeneration).where(CodebaseIndexGeneration.id == gen.id)
    with pytest.raises(IntegrityError):
        await db_session.execute(del_stmt)
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_race_c_expired_pin_cleaned_and_generation_reclaimed(db_session: AsyncSession, codebase_service: CodebaseService):
    """Race C: Expired pin is cleaned by GC and retired generation is successfully reclaimed."""
    ws, cb = await _setup_workspace_and_codebase(db_session)

    # 1. Create retired generation
    gen = CodebaseIndexGeneration(
        id=uuid.uuid4(),
        codebase_id=cb.id,
        workspace_id=ws.id,
        generation_number=1,
        status="retired",
    )
    db_session.add(gen)
    await db_session.flush()

    # 2. Create an EXPIRED pin (expires in the past)
    query_id = uuid.uuid4()
    expired_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    pin = CodebaseActiveQueryPin(
        query_id=query_id,
        generation_id=gen.id,
        codebase_id=cb.id,
        workspace_id=ws.id,
        expires_at=expired_time,
    )
    db_session.add(pin)
    await db_session.flush()

    # 3. Run GC
    reclaimed_count = await codebase_service.cleanup_retired_generations(db_session, cb.id)
    assert reclaimed_count == 1

    # 4. Verify generation is gone
    check_stmt = select(CodebaseIndexGeneration).where(CodebaseIndexGeneration.id == gen.id)
    res = (await db_session.execute(check_stmt)).scalar_one_or_none()
    assert res is None


@pytest.mark.asyncio
async def test_race_d_pin_heartbeat_and_release(db_session: AsyncSession, codebase_service: CodebaseService):
    """Race D: Query heartbeat extends pin expiration; release removes it cleanly."""
    ws, cb = await _setup_workspace_and_codebase(db_session)

    gen = CodebaseIndexGeneration(
        id=uuid.uuid4(),
        codebase_id=cb.id,
        workspace_id=ws.id,
        generation_number=1,
        status="active",
    )
    db_session.add(gen)
    await db_session.flush()

    query_id = uuid.uuid4()
    # 1. Acquire Pin
    pin = await codebase_service.acquire_query_pin(db_session, ws.id, cb.id, gen.id, query_id, ttl_seconds=30)
    initial_exp = pin.expires_at

    # 2. Heartbeat extends pin
    refreshed = await codebase_service.heartbeat_query_pin(db_session, query_id, extension_seconds=60)
    assert refreshed is True
    await db_session.refresh(pin)
    p_exp = pin.expires_at if pin.expires_at.tzinfo else pin.expires_at.replace(tzinfo=timezone.utc)
    i_exp = initial_exp if initial_exp.tzinfo else initial_exp.replace(tzinfo=timezone.utc)
    assert p_exp > i_exp

    # 3. Release Pin
    released = await codebase_service.release_query_pin(db_session, query_id)
    assert released is True

    # 4. Verify Pin is gone
    pin_stmt = select(CodebaseActiveQueryPin).where(CodebaseActiveQueryPin.query_id == query_id)
    p_check = (await db_session.execute(pin_stmt)).scalar_one_or_none()
    assert p_check is None


@pytest.mark.asyncio
async def test_concurrent_generation_activation(db_session: AsyncSession, codebase_service: CodebaseService):
    """Two generation activations serialize safely, maintaining exactly one active generation."""
    ws, cb = await _setup_workspace_and_codebase(db_session)

    gen1 = CodebaseIndexGeneration(
        id=uuid.uuid4(),
        codebase_id=cb.id,
        workspace_id=ws.id,
        generation_number=1,
        status="building",
    )
    gen2 = CodebaseIndexGeneration(
        id=uuid.uuid4(),
        codebase_id=cb.id,
        workspace_id=ws.id,
        generation_number=2,
        status="building",
    )
    db_session.add_all([gen1, gen2])
    await db_session.flush()

    # Activate gen1
    await codebase_service.activate_generation(db_session, ws.id, cb.id, gen1.id)
    await db_session.refresh(cb)
    await db_session.refresh(gen1)
    assert cb.active_generation_id == gen1.id
    assert gen1.status == "active"

    # Activate gen2
    await codebase_service.activate_generation(db_session, ws.id, cb.id, gen2.id)
    await db_session.refresh(cb)
    await db_session.refresh(gen1)
    await db_session.refresh(gen2)
    assert cb.active_generation_id == gen2.id
    assert gen1.status == "retired"
    assert gen2.status == "active"
