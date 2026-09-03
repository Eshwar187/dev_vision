# ADR 0003: PostgreSQL 16 with pgvector for Relational and Semantic Storage

## Status
Accepted

## Context
DevVision AI requires relational storage for users, projects, job logs, and metadata, as well as high-dimensional vector storage for document embeddings, codebase chunks, and semantic search.

Specialized vector databases (e.g. Pinecone, Milvus, Qdrant, Weaviate) introduce an additional stateful infrastructure component, separate authentication, synchronization failure modes (where SQL data and vector data get out of sync), and added SaaS operational cost.

## Decision
We use **PostgreSQL 16** with the **pgvector** extension as the single primary database for both relational data and vector embeddings.
- In Phase 0, the `vector` extension is enabled in PostgreSQL without locking into a fixed vector dimension.
- Schema migrations are managed deterministically via **Alembic** and **SQLAlchemy 2.0**.
- Identifiers use **UUIDv4** across all entity tables.

## Consequences
- **Positive**:
  - Unified database simplifies backups, point-in-time recovery, and local development.
  - Transactional integrity: relational records and vector embeddings can be committed or rolled back in a single atomic transaction.
  - Hybrid search: relational filters (`WHERE project_id = ...`) and vector similarity search (`<=>`) happen in a single query planner execution.
  - HNSW indexing delivers sub-10ms nearest neighbor queries at substantial scale.
- **Negative / Tradeoffs**:
  - Very large vector scales (tens of millions of vectors with high-frequency concurrent writes) require dedicated PostgreSQL tuning (`maintenance_work_mem`, shared buffers).
