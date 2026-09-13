# DevVision AI — Production Deployment & Operations Guide

## Overview

DevVision AI operates under a strict architectural contract:

> **"Zero external cloud AI APIs and fully self-hosted AI inference, with Supabase-managed PostgreSQL + pgvector."**

Key architectural guarantees:
- **100% Self-Hosted AI Inference**: Local BGE embedding models (`BAAI/bge-small-en-v1.5`), local BGE cross-encoder reranker (`BAAI/bge-reranker-base`), and local Ollama or `llama.cpp` inference (`qwen2.5-coder:7b-instruct-q4_K_M`). Zero OpenAI, zero Anthropic, zero Gemini, zero Cohere.
- **Supabase-Managed PostgreSQL + pgvector**: Managed high-availability database with native pgvector extension for dense vector storage and HNSW indexing, paired with PostgreSQL `tsvector` for sparse full-text search and exact Reciprocal Rank Fusion (RRF).
- **Connection Mode Separation**:
  - `DATABASE_URL`: Transaction Pooler (Port 6543) or Session Connection for high-throughput API traffic. Configured with `prepared_statement_cache_size: 0` for pooler compatibility.
  - `WORKER_DATABASE_URL`: Direct Connection (Port 5432) for background ingestion workers and Alembic migrations. Guarantees transactional row locks (`SELECT ... FOR UPDATE`), heartbeat lease renewal, monotonic fencing barriers, and atomic zero-downtime generation activation.
- **Multi-Tenant Isolation**: Tenant boundaries enforced via workspace-scoped schemas, row ownership predicates, and anti-enumeration defenses.

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
┌───────────────────────────┐       ┌───────────────────┐    ┌───────────────────┐
│ Supabase PostgreSQL 16    │       │ Redis 7           │    │ MinIO (S3)        │
│ + pgvector                │       │ (6379)            │    │ (9000 / 9001)     │
│ Port 6543 (Tx Pooler)     │       └─────────┬─────────┘    └─────────┬─────────┘
│ Port 5432 (Direct Conn)   │                 │                        │
└─────────┬─────────────────┘                 │                        │
          │                                   │                        │
          │ (Direct 5432)                     │                        │
          └───────────────────┬───────────────┴────────────────────────┘
                              │
                              ▼
                 ┌──────────────────────────┐
                 │  Worker Daemon Replicas  │
                 │  (Ingestion & GC Loop)   │
                 └────────────┬─────────────┘
                              │
                              ▼
                 ┌──────────────────────────┐
                 │ Local AI Inference Host  │
                 │ Ollama / llama.cpp       │
                 │ Port 11434               │
                 └──────────────────────────┘
```

---

## 2. Supabase PostgreSQL Configuration

### Step 1: Enable pgvector Extension in Supabase
In your Supabase project dashboard, navigate to **Database -> Extensions** or open the **SQL Editor** and execute:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Step 2: Obtain Supabase Connection Strings
In the Supabase dashboard (**Project Settings -> Database**):
1. **Transaction Pooler Connection** (Port `6543`, Mode: `Transaction`):
   ```
   postgresql+asyncpg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
   ```
   Use this for `DATABASE_URL` (API traffic).
2. **Direct Connection** (Port `5432`, Mode: `Session` / Direct):
   ```
   postgresql+asyncpg://postgres.[PROJECT_REF]:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres
   ```
   Use this for `WORKER_DATABASE_URL` (Worker leases, fencing tokens, and Alembic migrations).

---

## 3. Production Deployment via Docker Compose

### Prerequisites
- Docker Engine 24.0+ and Docker Compose v2.20+
- Host with at least 16GB RAM and 4+ CPU cores (NVIDIA GPU recommended for local inference)
- Local Ollama daemon running on host (e.g. `ollama serve` with `ollama pull qwen2.5-coder:7b-instruct-q4_K_M`)
- Active Supabase project with pgvector enabled

### Step 1: Configure Environment Variables
Create `.env` based on `.env.example`:
```bash
# Security Keys
SECRET_KEY=your_64_character_cryptographically_secure_random_key_here
REDIS_PASSWORD=your_production_redis_password_here
S3_ACCESS_KEY=your_minio_access_key
S3_SECRET_KEY=your_minio_secret_key

# Supabase Managed Database URLs
DATABASE_URL=postgresql+asyncpg://postgres.yourproject:yourpassword@aws-0-us-east-1.pooler.supabase.com:6543/postgres
WORKER_DATABASE_URL=postgresql+asyncpg://postgres.yourproject:yourpassword@db.yourproject.supabase.co:5432/postgres

# Storage & Cache
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
S3_ENDPOINT_URL=http://minio:9000
S3_BUCKET_NAME=devvision-documents

# 100% Self-Hosted Local AI Engine
LLM_BACKEND=ollama
LLM_BASE_URL=http://host.docker.internal:11434
LLM_MODEL=qwen2.5-coder:7b-instruct-q4_K_M
RAG_QUERY_TIMEOUT_SECONDS=60
EMBEDDING_MODEL_NAME=BAAI/bge-small-en-v1.5
RERANKER_MODEL_NAME=BAAI/bge-reranker-base
RERANKER_ENABLED=true
```

### Step 2: Apply Database Migrations
Run Alembic migrations using direct connection mode to ensure DDL execution and pgvector index creation:
```bash
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head
```

### Step 3: Launch Production Containers
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### Step 4: Verify Deployment Health
```bash
# Check shallow liveness probe
curl -f http://localhost:8000/health/live

# Check deep readiness probe (verifies Supabase DB, Redis, MinIO, and Ollama)
curl -f http://localhost:8000/health/ready

# Check Prometheus metrics
curl -s http://localhost:8000/metrics | grep rag_
```

---

## 4. Disaster Recovery & Backup Procedures

Logical backup and restore utilities are provided in `scripts/`:

### Creating a Logical Backup
To export a compressed, self-contained pgvector-preserving archive from Supabase:
```powershell
# PowerShell (Windows)
.\scripts\backup.ps1 -DatabaseUrl $env:WORKER_DATABASE_URL -OutputDir backups

# Bash (Linux/macOS)
./scripts/backup.sh backups
```
The script uses `pg_dump` with `--format=custom --compress=9 --clean --if-exists --no-owner --no-privileges` to preserve table schemas, HNSW vector indices, and relational integrity.

### Restoring from Backup
To restore a snapshot into a target database and verify pgvector integrity:
```powershell
# PowerShell (Windows)
.\scripts\restore.ps1 -BackupFile backups\devvision_backup_20260913_120000.dump -DatabaseUrl $env:WORKER_DATABASE_URL

# Bash (Linux/macOS)
./scripts/restore.sh backups/devvision_backup_20260913_120000.dump
```
Post-restore verification automatically checks:
1. `vector` extension status.
2. Total tables restored.
3. HNSW index validity.

---

## 5. Performance Benchmarking & Load Testing

A parameterized load testing tool is included at `backend/benchmarks/load_test.py`.

### Running Standalone Benchmark
```bash
python -m benchmarks.load_test --concurrency 5 --total-queries 50 --distribution zipfian
```
Measures:
- End-to-end RAG latency (P50, P95, P99).
- Hybrid retrieval latency (Dense, Sparse, RRF, Reranker).
- Local LLM generation duration.
- Error, timeout, and 429 rates.
- Ingestion throughput (chunks/sec, docs/min).
- Database connection pool utilization.

Results are printed in an ASCII table and saved as structured JSON reports in `backend/benchmarks/results/`.

### Running CI Performance Smoke Test
```bash
pytest benchmarks/test_benchmark_smoke.py -v
```

---

## 6. Production Readiness Checklist

Before going live:
- [ ] **Supabase pgvector**: Verified `CREATE EXTENSION IF NOT EXISTS vector;` executed in Supabase SQL Editor.
- [ ] **Dual Connection Strings**: Verified `DATABASE_URL` uses pooler (Port 6543) and `WORKER_DATABASE_URL` uses direct connection (Port 5432).
- [ ] **Migrations**: Executed `alembic upgrade head` to configure tables, HNSW indices, and constraints.
- [ ] **Local AI Models**: Downloaded `BAAI/bge-small-en-v1.5`, `BAAI/bge-reranker-base`, and `qwen2.5-coder:7b-instruct-q4_K_M`.
- [ ] **Readiness Check**: Confirmed `/health/ready` returns `200 OK` with `status: "healthy"`.
- [ ] **Rate Limiting**: Verified Redis sliding window with in-memory fallback enabled.
- [ ] **Log Sanitization**: Verified no raw prompts, tokens, or query texts are logged.
- [ ] **Metrics**: Verified Prometheus metrics available at `/metrics` with bounded cardinality.
- [ ] **Disaster Recovery**: Verified backup and restore scripts with test snapshot.
