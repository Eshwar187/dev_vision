import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from app.core.database import check_db_health, check_pgvector_installed
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
    redis: str
    storage: str


class ReadyResponse(BaseModel):
    status: str
    checks: DependencyChecks
    timestamp: str


@router.get(
    "/health/live",
    response_model=LiveResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe",
    description="Shallow health check to verify the FastAPI process is responsive.",
)
async def health_live() -> LiveResponse:
    return LiveResponse(
        status="ok",
        service="devvision-api",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/health/ready",
    response_model=ReadyResponse,
    summary="Readiness Probe",
    description="Deep health check verifying connectivity to PostgreSQL, pgvector, Redis, and MinIO/S3.",
)
async def health_ready(response: Response) -> ReadyResponse:
    # Run checks concurrently without blocking event loop
    db_task = asyncio.create_task(check_db_health())
    redis_task = asyncio.create_task(check_redis_health())
    storage_task = asyncio.to_thread(get_storage().check_health)

    db_ok, redis_ok, storage_ok = await asyncio.gather(db_task, redis_task, storage_task)
    pgvector_ok = await check_pgvector_installed() if db_ok else False

    checks = DependencyChecks(
        database="healthy" if db_ok else "unhealthy",
        pgvector="installed" if pgvector_ok else "missing",
        redis="healthy" if redis_ok else "unhealthy",
        storage="healthy" if storage_ok else "unhealthy",
    )

    all_healthy = db_ok and redis_ok and storage_ok
    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadyResponse(
        status="healthy" if all_healthy else "unhealthy",
        checks=checks,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )