from fastapi import APIRouter
from app.api.v1.endpoints import health, system

api_v1_router = APIRouter()

# Register health & system endpoints
api_v1_router.include_router(health.router)
api_v1_router.include_router(system.router)
