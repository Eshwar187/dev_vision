# DevVision AI — Production Deployment & Operations Guide

## Overview

DevVision AI is a production-grade, 100% self-hosted AI architecture featuring:
- Multi-tenant workspace isolation with role-based access control (RBAC).
- Local Hugging Face embedding models (`BAAI/bge-small-en-v1.5`, 384 dimensions).
- Local BGE cross-encoder reranker (`BAAI/bge-reranker-base`).
- Local Ollama or `llama.cpp` inference daemon (`qwen2.5-coder:7b-instruct-q4_K_M`).
- PostgreSQL with `pgvector` hybrid search (exact RRF fusion of dense vectors + sparse English `tsvector`).
- Distributed worker daemon with atomic row leasing and fencing tokens.
- Zero external AI APIs (no OpenAI, no Anthropic, no Cohere, no hosted vector DBs).

---

## 1. System Architecture & Topology

```
                  ┌───────────────────────────────┐
                  │          Reverse Proxy        │
                  │       (Nginx / Traefik)       │
                  └──────────────┬────────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 │                               │
                 ▼                               ▼
    ┌────────────────────────┐      ┌────────────────────────┐
    │     Frontend (Svelte)  │      │     Backend (FastAPI)  │
    │     Port 3000          │      │     Port 8000          │
    └────────────────────────┘      └────────────┬───────────┘
                                                 │
          ┌──────────────────────────────────────┼────────────────────────┐
          │                                      │                        │
          ▼                                      ▼                        ▼
┌───────────────────┐                  ┌───────────────────┐    ┌───────────────────┐
│ PostgreSQL 16     │                  │ Redis 7           │    │ MinIO (S3)        │
│ + pgvector (5432) │                  │ (6379)            │    │ (9000 / 9001)     │
└─────────┬─────────┘                  └─────────┬─────────┘    └─────────┬─────────┘
          │                                      │                        │
          └───────────────────┬──────────────────┴────────────────────────┘
                              │
                              ▼
                 ┌──────────────────────────┐
                 │  Worker Daemon Replicas  │
                 │  (Ingestion & GC Loop)   │
                 └────────────┬─────────────┘
                              │
                              ▼
                 ┌──────────────────────────┐
                 │ Local LLM Daemon         │
                 │ Ollama / llama.cpp       │
                 │ Port 11434               │
                 └──────────────────────────┘
```

---

## 2. Production Deployment via Docker Compose

### Prerequisites
- Docker Engine 24.0+ and Docker Compose v2.20+
- Host with at least 16GB RAM and 4+ CPU cores (8+ CPU cores recommended for local LLM inference)
- Local Ollama daemon running on host (e.g. `ollama serve` with `ollama pull qwen2.5-coder:7b-instruct-q4_K_M`)

### Step 1: Prepare Environment Variables
Copy `.env.example` to `.env` and configure strong secrets:
```bash
# Security Keys
SECRET_KEY=your_64_character_cryptographically_secure_random_key_here
POSTGRES_PASSWORD=your_production_postgres_password_here
REDIS_PASSWORD=your_production_redis_password_here
S3_ACCESS_KEY=your_minio_access_key
S3_SECRET_KEY=your_minio_secret_key

# Infrastructure URLs
DATABASE_URL=postgresql+asyncpg://devvision:${POSTGRES_PASSWORD}@postgres:5432/devvision
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
S3_ENDPOINT_URL=http://minio:9000
S3_BUCKET_NAME=devvision-documents

# Local AI Engine
LLM_BACKEND=ollama
LLM_BASE_URL=http://host.docker.internal:11434
LLM_MODEL=qwen2.5-coder:7b-instruct-q4_K_M
RAG_QUERY_TIMEOUT_SECONDS=60
```

### Step 2: Launch Production Services
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### Step 3: Run Database Migrations
```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

### Step 4: Verify Deployment Health
```bash
# Check shallow liveness probe
curl -f http://localhost:8000/health/live

# Check deep readiness probe
curl -f http://localhost:8000/ready

# Check Prometheus metrics
curl -s http://localhost:8000/metrics
```

---

## 3. Observability & Metrics Specification

DevVision AI exposes standard Prometheus text format metrics at `/metrics`:

| Metric Name | Type | Description |
| :--- | :--- | :--- |
| `devvision_rag_queries_total` | Counter | Total RAG queries labeled by `status` (`success`, `timeout`, `error`, `safe_refusal`) |
| `devvision_rag_query_duration_seconds` | Histogram | End-to-end query latency with cumulative buckets up to 60s |
| `devvision_rag_dense_retrieval_duration_seconds` | Histogram | Dense vector retrieval duration |
| `devvision_rag_sparse_retrieval_duration_seconds` | Histogram | Full-text tsvector retrieval duration |
| `devvision_rag_rerank_duration_seconds` | Histogram | Cross-encoder reranker inference duration |
| `devvision_rag_llm_duration_seconds` | Histogram | Local LLM inference duration |
| `devvision_rag_documents_ingested_total` | Counter | Total documents indexed by status (`completed`, `failed`) |
| `devvision_rag_generation_activations_total` | Counter | Total successful zero-downtime generation activations |
| `devvision_rag_worker_lease_failures_total` | Counter | Fencing token mismatches and lease expiration collisions |
| `devvision_rag_generation_gc_total` | Counter | Total retired/failed index generations cleaned up |

---

## 4. Rate Limiting & Operational Ceilings

### Sliding-Window Ceilings
- **RAG Queries**: 30 queries/minute per workspace.
- **Document Uploads**: 10 uploads/minute per workspace.
- **Document Reindexing**: 5 reindexes/minute per workspace.
- Exceeding limits returns `HTTP 429 Too Many Requests` with `Retry-After: <seconds>`.

### Request & Resource Ceilings
- **Max Document Size**: 20 MB payload limit enforced before parsing.
- **Max Extracted Text**: 10 MB text limit per document.
- **Max Query Length**: 2000 characters limit.
- **Max Retrieval Candidates**: `top_k <= 10` (query schema constraint).
- **RAG Execution Timeout**: 60 seconds hard ceiling via `asyncio.wait_for`.

---

## 5. Standalone Worker Daemon & Scaling

The worker daemon runs as an isolated process:
```bash
python -m app.modules.rag.worker_loop
```
- **Concurrency**: Scale horizontally by increasing replicas in `docker-compose.prod.yml` (`worker.deploy.replicas: N`).
- **Distributed Fencing**: Each document indexing generation holds a monotonic `fencing_token`. Stale writes from expired workers are rejected with zero chance of split-brain corruption.
- **Graceful Termination**: Handles `SIGTERM` and `SIGINT` by finishing the in-flight chunk batch and cleanly relinquishing leases.
- **Automated GC**: Runs every 10 minutes to prune generations older than 90 days or failed indexing attempts.

---

## 6. Disaster Recovery & Backup

### PostgreSQL + pgvector Backup
```bash
docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U devvision -d devvision --format=custom -f /var/lib/postgresql/data/backup_$(date +%Y%m%d).dump
```

### MinIO Object Storage Backup
```bash
docker run --rm -v $(pwd)/backup:/backup --network devvision_internal minio/mc:latest \
    mirror devvision_minio/devvision-documents /backup/devvision-documents
```
