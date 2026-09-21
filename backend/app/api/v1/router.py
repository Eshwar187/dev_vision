from fastapi import APIRouter
from app.api.v1.endpoints import auth, codebase, documents, github, health, rag, system, workspaces

api_v1_router = APIRouter()

# Register Phase 0 endpoints
api_v1_router.include_router(health.router)
api_v1_router.include_router(system.router)

# Register Phase 1 endpoints
api_v1_router.include_router(auth.router)
api_v1_router.include_router(workspaces.router)

# Register Phase 2 endpoints
api_v1_router.include_router(documents.router)

# Register Phase 3 endpoints
api_v1_router.include_router(rag.router)

# Register Phase 7 Codebase Intelligence & Code RAG endpoints
api_v1_router.include_router(codebase.router, prefix="/workspaces", tags=["Codebase Intelligence"])

# Register Phase 8 GitHub Integration endpoints
api_v1_router.include_router(github.callback_router, tags=["GitHub Integration"])
api_v1_router.include_router(github.router, prefix="/workspaces", tags=["GitHub Integration"])