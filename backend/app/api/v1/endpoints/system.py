from datetime import datetime, timezone
from fastapi import APIRouter
from pydantic import BaseModel
from app.core.config import get_settings

router = APIRouter(prefix="/system", tags=["System"])
settings = get_settings()


class SystemInfoResponse(BaseModel):
    app_name: str
    version: str
    environment: str
    debug: bool
    api_version: str
    timestamp: str


@router.get("/info", response_model=SystemInfoResponse, summary="System Information")
async def get_system_info() -> SystemInfoResponse:
    return SystemInfoResponse(
        app_name=settings.APP_NAME,
        version="0.1.0",
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
        api_version="v1",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
