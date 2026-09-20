"""
Unit tests for DevVision AI - Phase 7 Query Pin Lifecycle.

Proves:
1. Initial TTL = 300s (5 minutes).
2. Heartbeat interval = 60s.
3. Heartbeat extends pin up to the absolute 15-minute (900s) maximum query lifetime ceiling.
4. Heartbeat rejected once current time reaches or exceeds 15 minutes.
5. Heartbeat rejected if pin already expired.
6. _verify_pin raises ValidationException on expired or lifetime-exceeded pins.
7. query_codebase aborts at each of the 6 checkpoints if pin expires:
   - Checkpoint 1: Pre-dense retrieval
   - Checkpoint 2: Pre-sparse retrieval
   - Checkpoint 3: Pre-RRF fusion
   - Checkpoint 4: Pre-reranking
   - Checkpoint 5: Pre-LLM generation
   - Checkpoint 6: Pre-persistence
8. Expired pin causes query abort; no successful answer or audit records (CodebaseQuery, CodebaseQueryCitation) persisted.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationException
from app.modules.codebase.models import (
    Codebase,
    CodebaseActiveQueryPin,
    CodebaseIndexGeneration,
    CodebaseQuery,
    CodebaseQueryCitation,
)
from app.modules.codebase.retrieval import HybridCodeRetriever, RetrievedCodeCandidate
from app.modules.codebase.service import (
    CodebaseService,
    HEARTBEAT_INTERVAL,
    INITIAL_TTL,
    MAX_QUERY_LIFETIME,
)
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


async def _seed_workspace_codebase_and_gen(db_session: AsyncSession):
    ws = Workspace(id=uuid.uuid4(), name="Pin WS", slug=f"pin-ws-{uuid.uuid4().hex[:6]}")
    db_session.add(ws)
    await db_session.flush()

    cb = Codebase(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        name="Pin-Repo",
        is_indexed=False,
    )
    db_session.add(cb)
    await db_session.flush()

    gen = CodebaseIndexGeneration(
        id=uuid.uuid4(),
        codebase_id=cb.id,
        workspace_id=ws.id,
        generation_number=1,
        status="active",
        pipeline_version="1.0.0",
        embedding_model_revision="bge-small-en-v1.5",
    )
    db_session.add(gen)
    await db_session.flush()

    cb.active_generation_id = gen.id
    cb.is_indexed = True
    await db_session.flush()
    return ws, cb, gen


@pytest.mark.asyncio
async def test_constants_configured_correctly():
    """Verify SLA constants."""
    assert INITIAL_TTL == 300  # 5 minutes
    assert HEARTBEAT_INTERVAL == 60  # 60 seconds
    assert MAX_QUERY_LIFETIME == 900  # 15 minutes


@pytest.mark.asyncio
async def test_pin_initial_ttl_is_5_minutes(db_session: AsyncSession, codebase_service: CodebaseService):
    """Prove initial TTL is 5 minutes (300 seconds)."""
    ws, cb, gen = await _seed_workspace_codebase_and_gen(db_session)
    query_id = uuid.uuid4()

    pin = await codebase_service.acquire_query_pin(
        db_session, ws.id, cb.id, gen.id, query_id, ttl_seconds=INITIAL_TTL
    )

    created_at = pin.created_at if pin.created_at.tzinfo else pin.created_at.replace(tzinfo=timezone.utc)
    expires_at = pin.expires_at if pin.expires_at.tzinfo else pin.expires_at.replace(tzinfo=timezone.utc)

    ttl_delta = (expires_at - created_at).total_seconds()
    assert abs(ttl_delta - 300) < 2.0


@pytest.mark.asyncio
async def test_heartbeat_extends_pin_under_15_minutes(db_session: AsyncSession, codebase_service: CodebaseService):
    """Prove heartbeat extends pin expiration when within 15 minutes."""
    ws, cb, gen = await _seed_workspace_codebase_and_gen(db_session)
    query_id = uuid.uuid4()

    pin = await codebase_service.acquire_query_pin(db_session, ws.id, cb.id, gen.id, query_id, ttl_seconds=60)
    initial_exp = pin.expires_at if pin.expires_at.tzinfo else pin.expires_at.replace(tzinfo=timezone.utc)

    # Perform heartbeat with 300s extension
    extended = await codebase_service.heartbeat_query_pin(db_session, query_id, extension_seconds=300)
    assert extended is True

    await db_session.refresh(pin)
    new_exp = pin.expires_at if pin.expires_at.tzinfo else pin.expires_at.replace(tzinfo=timezone.utc)
    assert new_exp > initial_exp


@pytest.mark.asyncio
async def test_heartbeat_capped_at_absolute_15_minute_ceiling(db_session: AsyncSession, codebase_service: CodebaseService):
    """Prove heartbeat cannot extend beyond 15 minutes from pin creation."""
    ws, cb, gen = await _seed_workspace_codebase_and_gen(db_session)
    query_id = uuid.uuid4()

    now = datetime.now(timezone.utc)
    # Pin created 13 minutes ago (780 seconds)
    created_time = now - timedelta(seconds=780)
    pin = CodebaseActiveQueryPin(
        query_id=query_id,
        generation_id=gen.id,
        codebase_id=cb.id,
        workspace_id=ws.id,
        created_at=created_time,
        heartbeat_at=now,
        expires_at=now + timedelta(seconds=60),  # still active
    )
    db_session.add(pin)
    await db_session.flush()

    # Heartbeat requesting 300s extension. Since 780 + 300 = 1080 > 900, must be capped at 900 (remaining 120s from created_at)
    extended = await codebase_service.heartbeat_query_pin(db_session, query_id, extension_seconds=300)
    assert extended is True

    await db_session.refresh(pin)
    pin_exp = pin.expires_at if pin.expires_at.tzinfo else pin.expires_at.replace(tzinfo=timezone.utc)
    absolute_deadline = created_time + timedelta(seconds=MAX_QUERY_LIFETIME)

    assert abs((pin_exp - absolute_deadline).total_seconds()) < 2.0


@pytest.mark.asyncio
async def test_heartbeat_fails_at_or_past_15_minutes(db_session: AsyncSession, codebase_service: CodebaseService):
    """Prove heartbeat returns False when current time reaches or exceeds 15 minutes."""
    ws, cb, gen = await _seed_workspace_codebase_and_gen(db_session)
    query_id = uuid.uuid4()

    now = datetime.now(timezone.utc)
    # Pin created 15 minutes and 5 seconds ago
    created_time = now - timedelta(seconds=905)
    pin = CodebaseActiveQueryPin(
        query_id=query_id,
        generation_id=gen.id,
        codebase_id=cb.id,
        workspace_id=ws.id,
        created_at=created_time,
        heartbeat_at=now,
        expires_at=now + timedelta(seconds=60),
    )
    db_session.add(pin)
    await db_session.flush()

    extended = await codebase_service.heartbeat_query_pin(db_session, query_id, extension_seconds=60)
    assert extended is False


@pytest.mark.asyncio
async def test_heartbeat_fails_if_pin_expired(db_session: AsyncSession, codebase_service: CodebaseService):
    """Prove heartbeat returns False if pin has already expired."""
    ws, cb, gen = await _seed_workspace_codebase_and_gen(db_session)
    query_id = uuid.uuid4()

    now = datetime.now(timezone.utc)
    pin = CodebaseActiveQueryPin(
        query_id=query_id,
        generation_id=gen.id,
        codebase_id=cb.id,
        workspace_id=ws.id,
        created_at=now - timedelta(seconds=200),
        heartbeat_at=now - timedelta(seconds=100),
        expires_at=now - timedelta(seconds=10),  # Expired
    )
    db_session.add(pin)
    await db_session.flush()

    extended = await codebase_service.heartbeat_query_pin(db_session, query_id, extension_seconds=60)
    assert extended is False


@pytest.mark.asyncio
async def test_verify_pin_rejections(db_session: AsyncSession, codebase_service: CodebaseService):
    """Prove _verify_pin raises ValidationException on expired or over-15m pins."""
    ws, cb, gen = await _seed_workspace_codebase_and_gen(db_session)

    # 1. Non-existent pin
    with pytest.raises(ValidationException, match="Query pin expired or lost"):
        await codebase_service._verify_pin(db_session, uuid.uuid4())

    # 2. Expired pin
    now = datetime.now(timezone.utc)
    q2 = uuid.uuid4()
    p2 = CodebaseActiveQueryPin(
        query_id=q2,
        generation_id=gen.id,
        codebase_id=cb.id,
        workspace_id=ws.id,
        created_at=now - timedelta(seconds=100),
        heartbeat_at=now - timedelta(seconds=50),
        expires_at=now - timedelta(seconds=5),
    )
    db_session.add(p2)
    await db_session.flush()
    with pytest.raises(ValidationException, match="Query pin expired or lost"):
        await codebase_service._verify_pin(db_session, q2)

    # 3. Beyond 15-minute lifetime
    q3 = uuid.uuid4()
    p3 = CodebaseActiveQueryPin(
        query_id=q3,
        generation_id=gen.id,
        codebase_id=cb.id,
        workspace_id=ws.id,
        created_at=now - timedelta(seconds=905),
        heartbeat_at=now,
        expires_at=now + timedelta(seconds=100),
    )
    db_session.add(p3)
    await db_session.flush()
    with pytest.raises(ValidationException, match="Query lifetime exceeded maximum limit"):
        await codebase_service._verify_pin(db_session, q3)


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_checkpoint", [1, 2, 3, 4, 5, 6])
async def test_query_codebase_aborts_at_each_checkpoint_and_persists_no_audit(
    db_session: AsyncSession, codebase_service: CodebaseService, fail_checkpoint: int
):
    """
    Prove that if the pin expires before ANY of the 6 checkpoints:
    1: pre-dense
    2: pre-sparse
    3: pre-RRF
    4: pre-rerank
    5: pre-LLM
    6: pre-persistence
    The query immediately aborts, raises ValidationException, and leaves NO query or citation in the DB.
    """
    ws, cb, gen = await _seed_workspace_codebase_and_gen(db_session)

    # Prepare candidate snippet
    cand = RetrievedCodeCandidate(
        chunk_id=uuid.uuid4(),
        generation_id=gen.id,
        file_id=uuid.uuid4(),
        file_path="main.py",
        language="python",
        start_line=1,
        end_line=10,
        scope_path="main",
        content="def hello(): return 'world'",
        content_hash="hash123",
        token_count=10,
        score=0.95,
        rerank_score=0.95,
    )

    codebase_service.retriever.retrieve_dense = AsyncMock(return_value=[cand])
    codebase_service.retriever.retrieve_sparse = AsyncMock(return_value=[cand])
    codebase_service.retriever.fuse_rrf = MagicMock(return_value=[cand])
    codebase_service.retriever.rerank = AsyncMock(return_value=[cand])
    codebase_service.llm_client.generate_response = AsyncMock(
        return_value="According to [SNIPPET_1], it returns world."
    )

    call_count = 0
    original_verify = codebase_service._verify_pin

    async def mock_verify(session, q_id):
        nonlocal call_count
        call_count += 1
        if call_count == fail_checkpoint:
            # Expire pin in DB to trigger actual verification failure
            pin_stmt = select(CodebaseActiveQueryPin).where(CodebaseActiveQueryPin.query_id == q_id)
            p = (await session.execute(pin_stmt)).scalar_one()
            p.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
            await session.flush()
        await original_verify(session, q_id)

    with patch.object(codebase_service, "_verify_pin", side_effect=mock_verify):
        with pytest.raises(ValidationException):
            await codebase_service.query_codebase(
                session=db_session,
                workspace_id=ws.id,
                codebase_id=cb.id,
                query="What does hello return?",
            )

    # Assert NO historical audit record was persisted
    q_stmt = select(CodebaseQuery).where(CodebaseQuery.codebase_id == cb.id)
    queries = (await db_session.execute(q_stmt)).scalars().all()
    assert len(queries) == 0, f"No query records should be persisted on abort at checkpoint {fail_checkpoint}"

    cit_stmt = select(CodebaseQueryCitation).where(CodebaseQueryCitation.workspace_id == ws.id)
    cits = (await db_session.execute(cit_stmt)).scalars().all()
    assert len(cits) == 0, f"No citations should be persisted on abort at checkpoint {fail_checkpoint}"

    # Assert pin was cleaned up in finally block
    pins_stmt = select(CodebaseActiveQueryPin).where(CodebaseActiveQueryPin.codebase_id == cb.id)
    pins = (await db_session.execute(pins_stmt)).scalars().all()
    assert len(pins) == 0, f"Active pin should be cleaned up on abort at checkpoint {fail_checkpoint}"
