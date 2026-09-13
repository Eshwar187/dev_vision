import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from app.core.database import Base

import app.modules.identity.models  # noqa: F401
import app.modules.workspaces.models  # noqa: F401
import app.modules.documents.models  # noqa: F401
import app.modules.rag.models  # noqa: F401

benchmark_test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

BenchmarkTestingSessionLocal = async_sessionmaker(
    bind=benchmark_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

@pytest_asyncio.fixture(autouse=True)
async def init_benchmark_test_db():
    async with benchmark_test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with benchmark_test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
