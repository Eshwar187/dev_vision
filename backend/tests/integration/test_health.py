from unittest.mock import patch
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_live(async_client: AsyncClient):
    response = await async_client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "devvision-api"
    assert "timestamp" in data
    assert "x-request-id" in response.headers
    assert "x-process-time-ms" in response.headers


@pytest.mark.asyncio
async def test_health_ready_all_healthy(async_client: AsyncClient):
    with patch("app.api.v1.endpoints.health.check_db_health", return_value=True), \
         patch("app.api.v1.endpoints.health.check_pgvector_installed", return_value=True), \
         patch("app.api.v1.endpoints.health.check_redis_health", return_value=True), \
         patch("app.api.v1.endpoints.health.get_storage") as mock_storage:

        mock_instance = mock_storage.return_value
        mock_instance.check_health.return_value = True

        response = await async_client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["checks"]["database"] == "healthy"
        assert data["checks"]["pgvector"] == "installed"
        assert data["checks"]["redis"] == "healthy"
        assert data["checks"]["storage"] == "healthy"


@pytest.mark.asyncio
async def test_health_ready_degraded(async_client: AsyncClient):
    with patch("app.api.v1.endpoints.health.check_db_health", return_value=False), \
         patch("app.api.v1.endpoints.health.check_redis_health", return_value=True), \
         patch("app.api.v1.endpoints.health.get_storage") as mock_storage:

        mock_instance = mock_storage.return_value
        mock_instance.check_health.return_value = True

        response = await async_client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["database"] == "unhealthy"


@pytest.mark.asyncio
async def test_system_info(async_client: AsyncClient):
    response = await async_client.get("/api/v1/system/info")
    assert response.status_code == 200
    data = response.json()
    assert data["app_name"] == "DevVision AI"
    assert data["version"] == "0.1.0"
    assert data["api_version"] == "v1"
