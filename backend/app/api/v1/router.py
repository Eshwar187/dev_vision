from fastapi import APIRouter
from app.api.v1.endpoints import auth, documents, health, system, workspaces

api_v1_router = APIRouter()

# Register Phase 0 endpoints
api_v1_router.include_router(health.router)
api_v1_router.include_router(system.router)

# Register Phase 1 endpoints
api_v1_router.include_router(auth.router)
api_v1_router.include_router(workspaces.router)

# Register Phase 2 endpoints
api_v1_router.include_router(documents.router)