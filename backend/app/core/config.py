from functools import lru_cache
from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "DevVision AI"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "devvision_super_secret_dev_key_change_in_production_32chars_min"
    API_V1_STR: str = "/api/v1"

    # Server Networking & CORS
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    # PostgreSQL + pgvector
    POSTGRES_USER: str = "devvision"
    POSTGRES_PASSWORD: str = "devvision_password"
    POSTGRES_DB: str = "devvision"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = "postgresql+asyncpg://devvision:devvision_password@localhost:5432/devvision"
    DATABASE_SYNC_URL: str = "postgresql+psycopg2://devvision:devvision_password@localhost:5432/devvision"

    # Database Pool Settings
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"

    # Object Storage (MinIO / S3-compatible)
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_NAME: str = "devvision-local"
    S3_REGION: str = "us-east-1"
    S3_SECURE: bool = False

    # Authentication & Sessions
    SESSION_COOKIE_NAME: str = "devvision_session"
    CSRF_COOKIE_NAME: str = "devvision_csrf"
    SESSION_MAX_AGE_SECONDS: int = 60 * 60 * 24 * 7  # 7 days fixed
    COOKIE_SECURE: bool = False  # Set to True in production
    COOKIE_SAMESITE: str = "lax"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def cookie_secure_effective(self) -> bool:
        return self.COOKIE_SECURE or self.is_production

    # RAG & AI Configuration (100% Self-Hosted)
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_MODEL_VERSION: str = "5c38ec7"
    EMBEDDING_DIMENSION: int = 384
    
    RERANKER_ENABLED: bool = True
    RERANKER_MODEL_NAME: str = "BAAI/bge-reranker-base"
    RERANKER_MODEL_VERSION: str = "2cb221b"
    
    LLM_BACKEND: str = "ollama"  # "ollama" or "llamacpp_server"
    LLM_BASE_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "qwen2.5-coder:7b-instruct-q4_K_M"
    LLM_REQUEST_TIMEOUT_SECONDS: int = 45
    LLM_MAX_RETRIES: int = 1
    
    RAG_HISTORY_RETENTION_DAYS: int = 90
    RAG_PROCESSING_LEASE_SECONDS: int = 60
    RAG_PROCESSING_HEARTBEAT_SECONDS: int = 15

    # Resource Limits & Timeouts (Phase 4 Hardening)
    MAX_UPLOAD_SIZE_BYTES: int = 20 * 1024 * 1024  # 20 MB
    MAX_EXTRACTED_TEXT_BYTES: int = 10 * 1024 * 1024  # 10 MB
    MAX_DOCUMENT_PAGES: int = 500
    MAX_CHUNKS_PER_DOCUMENT: int = 2000
    MAX_QUERY_LENGTH_CHARS: int = 2000
    MAX_RETRIEVAL_CANDIDATES: int = 100
    MAX_CONCURRENT_INGESTION_JOBS: int = 5
    MAX_EMBEDDING_BATCH_SIZE: int = 64
    RAG_QUERY_TIMEOUT_SECONDS: int = 60

    # Rate Limiting (Phase 4 Operational Resilience)
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_RAG_QUERIES_PER_MINUTE: int = 30
    RATE_LIMIT_UPLOADS_PER_MINUTE: int = 10
    RATE_LIMIT_REINDEX_PER_MINUTE: int = 5

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" or "console"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()