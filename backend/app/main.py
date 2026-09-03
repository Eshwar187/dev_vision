from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.endpoints import health
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.database import engine
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import get_logger, setup_logging
from app.core.middleware import RequestCorrelationMiddleware
from app.core.redis import close_redis_client, get_redis_client

settings = get_settings()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager handling startup & graceful shutdown."""
    setup_logging()
    logger.info(
        "Starting DevVision AI API",
        app_name=settings.APP_NAME,
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
    )

    # Initialize Redis connection pool
    try:
        get_redis_client()
        logger.info("Redis client initialized.")
    except Exception as exc:
        logger.warning("Redis initialization deferred", error=str(exc))

    yield

    logger.info("Shutting down DevVision AI API...")
    await close_redis_client()
    await engine.dispose()
    logger.info("Database connection engine disposed.")


def create_application() -> FastAPI:
    """FastAPI Application Factory."""
    app = FastAPI(
        title=settings.APP_NAME,
        description="DevVision AI - Multimodal Developer Copilot Backend API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time-MS"],
    )

    # Request ID and Timing Middleware
    app.add_middleware(RequestCorrelationMiddleware)

    # Centralized Exception Handlers
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Top-level Health Probes (for Docker/Kubernetes container orchestrators)
    app.include_router(health.router)

    # Versioned API routes
    app.include_router(api_v1_router, prefix=settings.API_V1_STR)

    return app


app = create_application()