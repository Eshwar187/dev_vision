"""PostgreSQL concurrency, locking, and constraint verification tests for GitHub Integration.
Executes exclusively when TEST_DATABASE_URL is provided (e.g. Supabase PostgreSQL).
Honestly skips when TEST_DATABASE_URL is not set.
"""

import os
import uuid
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.exceptions import ConflictException
from app.modules.github.models import GitHubInstallation, GitHubRepository


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="PostgreSQL verification: NOT RUN -- TEST_DATABASE_URL not configured.",
)
@pytest.mark.asyncio
async def test_postgres_github_installation_global_uniqueness():
    """Verify that PostgreSQL strictly enforces global installation_id uniqueness across workspaces."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # Create two distinct test workspaces and users
        test_suffix = uuid.uuid4().hex[:6]
        user1_id = uuid.uuid4()
        user2_id = uuid.uuid4()
        ws1_id = uuid.uuid4()
        ws2_id = uuid.uuid4()

        # Direct SQL setup to test real PostgreSQL constraints
        await session.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, is_active, created_at, updated_at) "
                "VALUES (:u1, :e1, 'pw', true, NOW(), NOW()), (:u2, :e2, 'pw', true, NOW(), NOW())"
            ),
            {"u1": user1_id, "e1": f"u1_{test_suffix}@example.com", "u2": user2_id, "e2": f"u2_{test_suffix}@example.com"},
        )
        await session.execute(
            text(
                "INSERT INTO workspaces (id, name, owner_id, created_at, updated_at) "
                "VALUES (:w1, :n1, :u1, NOW(), NOW()), (:w2, :n2, :u2, NOW(), NOW())"
            ),
            {"w1": ws1_id, "n1": f"ws1_{test_suffix}", "u1": user1_id, "w2": ws2_id, "n2": f"ws2_{test_suffix}", "u2": user2_id},
        )
        await session.commit()

        shared_inst_id = 888777666

        # Insert installation in Workspace 1
        inst1 = GitHubInstallation(
            workspace_id=ws1_id,
            installation_id=shared_inst_id,
            account_login=f"org_{test_suffix}",
            account_id=12345,
            account_type="Organization",
            installer_github_user_id=999,
            installer_github_user_login="installer",
            installed_by_user_id=user1_id,
        )
        session.add(inst1)
        await session.commit()

        # Attempt to insert same installation_id in Workspace 2 -> PostgreSQL constraint violation
        inst2 = GitHubInstallation(
            workspace_id=ws2_id,
            installation_id=shared_inst_id,
            account_login=f"org_{test_suffix}",
            account_id=12345,
            account_type="Organization",
            installer_github_user_id=999,
            installer_github_user_login="installer",
            installed_by_user_id=user2_id,
        )
        session.add(inst2)

        with pytest.raises(Exception) as exc_info:
            await session.commit()

        assert "uq_github_inst_global_id" in str(exc_info.value) or "unique" in str(exc_info.value).lower()
        await session.rollback()

    await engine.dispose()
