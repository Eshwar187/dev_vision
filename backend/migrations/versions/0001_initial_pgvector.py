"""Initial database migration: Enable uuid-ossp and pgvector extensions

Revision ID: 0001_initial_pgvector
Revises: 
Create Date: 2026-09-03 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial_pgvector"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable uuid-ossp extension for UUID generation
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    # Enable pgvector extension for high-dimensional vector embeddings
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")


def downgrade() -> None:
    # Drop vector extension
    op.execute("DROP EXTENSION IF EXISTS vector;")
    # Drop uuid-ossp extension
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp";')
