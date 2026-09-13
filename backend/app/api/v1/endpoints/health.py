import asyncio
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.database import check_db_health, check_migrations_ready, check_pgvector_installed
from app.core.metrics import metrics_registry
from app.core.redis import check_redis_health
from app.core.storage import get_storage

router = APIRouter(tags=["Health"])


class LiveResponse(BaseModel):
    status: str
    service: str
    timestamp: str


class DependencyChecks(BaseModel):
    database: str
    pgvector: str
    migrations: str
    redis: str
    storage: str
    embedding_model: str
    llm_runtime: str


class ReadyResponse(BaseModel):
    status: str
    checks: DependencyChecks
    timestamp: str


async def check_llm_ready() -> str:
    """Checks if the local LLM daemon (Ollama / llama.cpp) is responsive with a strict timeout."""
    settings = get_settings()
    url = settings.LLM_BASE_URL.rstrip("/")
    probe_url = f"{url}/api/tags" if settings.LLM_BACKEND == "ollama" else f"{url}/health"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(probe_url)
            if resp.status_code < 500:
                return "healthy"
            return "unhealthy"
    except Exception:
        return "unreachable"


def check_embedding_model_ready() -> str:
    """Verifies that the self-hosted embedding model can be instantiated without running expensive batch inference."""
    try:
        from app.modules.rag.embeddings import BgeEmbeddingModel
        model = BgeEmbeddingModel()
        return "ready" if model is not None else "unavailable"
    except Exception:
        return "uninitialized"


@router.get(
    "/health",
    response_model=LiveResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe",
    description="Shallow health check indicating the FastAPI process is alive.",
)
@router.get(
    "/health/live",
    response_model=LiveResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe (Alias)",
    include_in_schema=False,
)
async def health_live() -> LiveResponse:
    return LiveResponse(
        status="ok",
        service="devvision-api",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/ready",
    response_model=ReadyResponse,
    summary="Readiness Probe",
    description="Deep dependency probe verifying database, pgvector, migrations, storage, embedding model, and local LLM daemon.",
)
@router.get(
    "/health/ready",
    response_model=ReadyResponse,
    summary="Readiness Probe (Alias)",
    include_in_schema=False,
)
async def health_ready(response: Response) -> ReadyResponse:
    # Check db first so migration probe doesn't attempt direct connection if DB is down/mocked
    db_ok = await check_db_health()
    pgvector_ok = await check_pgvector_installed() if db_ok else False
    migrations_ok = await check_migrations_ready() if db_ok else False

    redis_task = asyncio.create_task(check_redis_health())
    storage_task = asyncio.to_thread(get_storage().check_health)
    llm_task = asyncio.create_task(check_llm_ready())
    embed_task = asyncio.to_thread(check_embedding_model_ready)

    redis_ok, storage_ok, llm_status, embed_status = await asyncio.gather(
        redis_task, storage_task, llm_task, embed_task
    )

    checks = DependencyChecks(
        database="healthy" if db_ok else "unhealthy",
        pgvector="installed" if pgvector_ok else "missing",
        migrations="applied" if migrations_ok else "pending_or_missing",
        redis="healthy" if redis_ok else "unhealthy",
        storage="healthy" if storage_ok else "unhealthy",
        embedding_model=embed_status,
        llm_runtime=llm_status,
    )

    # Core operational readiness: database and storage are mandatory for base operations
    core_healthy = db_ok and storage_ok
    if not core_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadyResponse(
        status="healthy" if core_healthy else "unhealthy",
        checks=checks,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Prometheus Metrics",
    description="Exposes application and RAG pipeline metrics in standard Prometheus/OpenMetrics text format.",
)
async def get_metrics() -> PlainTextResponse:
    content = metrics_registry.generate_exposition()
    return PlainTextResponse(content, media_type="text/plain; version=0.0.4; charset=utf-8")