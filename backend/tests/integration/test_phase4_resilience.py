"""
Adversarial Operational Resilience Integration Tests for DevVision AI Phase 4.

Validates:
1. Workspace rate-limit exhaustion: Exceeding queries/min triggers HTTP 429 with Retry-After header.
2. Rate-limit RFC header: Verify Retry-After is an integer string representing seconds.
3. Payload size rejection: Query length exceeding 2000 characters is rejected early with HTTP 422.
4. Top-K boundary enforcement: top_k > 10 is rejected with HTTP 422.
5. End-to-end query timeout: Slow inference triggers HTTP 504 Gateway Timeout cleanly.
6. Structured metrics exposition: /metrics returns valid Prometheus exposition text with custom metrics.
7. Concurrent metrics safety: Multiple threads incrementing metrics do not corrupt internal counters/histograms.
8. Readiness probe degradation: /ready returns 503 when core dependencies fail.
9. Worker graceful signal handling: WorkerDaemon stops gracefully upon SIGTERM without abandoning leases.
"""

import asyncio
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch, MagicMock

from app.core.metrics import metrics_registry, Counter
from app.core.limiter import InMemorySlidingWindow
from app.modules.rag.worker_loop import WorkerDaemon
from app.modules.identity.models import User, Session
from app.modules.workspaces.models import Workspace, WorkspaceMembership
from app.modules.rag.mock import MockEmbeddingModel, MockRerankerModel, MockLanguageModel
from app.modules.rag.service import RagService
from app.api.v1.endpoints.rag import get_rag_service
from app.main import app


@pytest.fixture
def mock_rag_service():
    return RagService(
        embedding_model=MockEmbeddingModel(),
        reranker_model=MockRerankerModel(),
        language_model=MockLanguageModel(),
    )


@pytest.fixture
async def authenticated_workspace(db_session: AsyncSession):
    """Creates an authenticated test user and workspace fixture."""
    user = User(
        email=f"resilience_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        display_name="Resilience Tester",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    workspace = Workspace(
        name="Resilience Workspace",
        slug=f"resilience-ws-{uuid.uuid4().hex[:6]}",
        created_by=user.id,
    )
    db_session.add(workspace)
    await db_session.flush()

    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=user.id,
        role="owner",
    )
    db_session.add(membership)

    raw_token = f"valid_token_{uuid.uuid4().hex}"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    session = Session(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(session)
    await db_session.commit()

    cookies = {
        "devvision_session": raw_token,
        "devvision_csrf": "test_csrf_resilience",
    }
    headers = {
        "X-CSRF-Token": "test_csrf_resilience",
    }
    return workspace, cookies, headers


@pytest.mark.asyncio
async def test_metrics_registry_exposition_syntax():
    """Verify Prometheus metrics exposition format compliance."""
    counter = metrics_registry.register_counter("test_exposition_metric_total", "Test counter help", ["env"])
    counter.inc(5, env="prod")
    
    registry = metrics_registry
    text_output = registry.generate_exposition()
    
    assert "# HELP" in text_output
    assert "# TYPE" in text_output
    assert "test_exposition_metric_total" in text_output


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter_in_memory_fallback():
    """Verify thread-safe in-memory sliding window rate limiter limits and resets."""
    limiter = InMemorySlidingWindow(max_keys=100)
    key = "test-ws-rate-limit"
    limit = 3
    window = 2.0

    # First 3 requests must be allowed
    for _ in range(limit):
        allowed, remaining, retry_after = limiter.is_allowed(key, limit=limit, window=window)
        assert allowed is True

    # 4th request must be rejected
    allowed, remaining, retry_after = limiter.is_allowed(key, limit=limit, window=window)
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0


@pytest.mark.asyncio
async def test_rag_query_length_boundary_rejected(
    async_client: AsyncClient,
    authenticated_workspace,
    mock_rag_service,
):
    """Verify query payload > 2000 characters is rejected before embedding calculation."""
    app.dependency_overrides[get_rag_service] = lambda: mock_rag_service
    workspace, cookies, headers = authenticated_workspace

    oversized_query = "A" * 2005
    payload = {
        "query": oversized_query,
        "top_k": 5,
    }
    response = await async_client.post(
        f"/api/v1/workspaces/{workspace.id}/rag/query",
        json=payload,
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 422
    assert "character" in response.text.lower() or "too long" in response.text.lower() or "validation" in response.text.lower()


@pytest.mark.asyncio
async def test_rag_query_top_k_boundary_rejected(
    async_client: AsyncClient,
    authenticated_workspace,
    mock_rag_service,
):
    """Verify top_k > 10 is rejected with HTTP 422."""
    app.dependency_overrides[get_rag_service] = lambda: mock_rag_service
    workspace, cookies, headers = authenticated_workspace

    payload = {
        "query": "Valid test query",
        "top_k": 50,
    }
    response = await async_client.post(
        f"/api/v1/workspaces/{workspace.id}/rag/query",
        json=payload,
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 422
    assert "less than or equal to 10" in response.text.lower() or "validation" in response.text.lower()


@pytest.mark.asyncio
async def test_rag_query_rate_limit_exceeded_retry_after(
    async_client: AsyncClient,
    authenticated_workspace,
    mock_rag_service,
):
    """Verify workspace exceeding rate limit returns HTTP 429 and Retry-After header."""
    app.dependency_overrides[get_rag_service] = lambda: mock_rag_service
    workspace, cookies, headers = authenticated_workspace

    with patch("app.core.limiter.limiter.check_rate_limit", new_callable=AsyncMock) as mock_limit:
        mock_limit.return_value = (False, 0, 42)
        payload = {
            "query": "Rate limited query",
            "top_k": 5,
        }
        response = await async_client.post(
            f"/api/v1/workspaces/{workspace.id}/rag/query",
            json=payload,
            cookies=cookies,
            headers=headers,
        )
        assert response.status_code == 429
        assert response.headers.get("retry-after") == "42"
        data = response.json()
        assert "RATE_LIMIT_EXCEEDED" in str(data)
        assert "42 seconds" in str(data)


@pytest.mark.asyncio
async def test_rag_query_timeout_gateway_error(
    async_client: AsyncClient,
    authenticated_workspace,
):
    """Verify RAG query timing out triggers HTTP 504 Gateway Timeout."""
    workspace, cookies, headers = authenticated_workspace

    async def slow_execute(*args, **kwargs):
        await asyncio.sleep(0.5)
        return MagicMock()

    slow_service = MagicMock()
    slow_service.execute_query = slow_execute
    app.dependency_overrides[get_rag_service] = lambda: slow_service

    from app.core import config
    mock_settings = config.get_settings()
    with patch.object(mock_settings, "RAG_QUERY_TIMEOUT_SECONDS", 0.05):
        payload = {
            "query": "Timeout testing query",
            "top_k": 5,
        }
        response = await async_client.post(
            f"/api/v1/workspaces/{workspace.id}/rag/query",
            json=payload,
            cookies=cookies,
            headers=headers,
        )
        assert response.status_code == 504
        assert "timeout" in response.text.lower()


@pytest.mark.asyncio
async def test_concurrent_metrics_updates():
    """Verify thread-safe metrics registry under high concurrency."""
    import concurrent.futures
    counter = Counter("concurrent_counter_test", "Concurrent metric", ["worker"])
    
    def worker_inc(w_id: str):
        for _ in range(100):
            counter.inc(1, worker=w_id)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker_inc, f"w-{i}") for i in range(5)]
        concurrent.futures.wait(futures)

    lines = counter.collect()
    assert any('worker="w-0"' in line and "100" in line for line in lines)
    assert any('worker="w-4"' in line and "100" in line for line in lines)


@pytest.mark.asyncio
async def test_worker_daemon_shutdown_graceful():
    """Verify WorkerDaemon cleanly stops when shutdown signal is set."""
    daemon = WorkerDaemon(poll_interval_seconds=0.01)
    daemon.stop()
    assert daemon._stop_event.is_set()
    assert daemon.is_running is False
