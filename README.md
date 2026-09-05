# DevVision AI — Multimodal Developer Copilot

DevVision AI is a production-oriented multimodal AI copilot built on a **modular monolith** architecture. It provides an enterprise-ready foundation for Document RAG, Codebase Intelligence, GitHub Automation, Computer Vision, Voice, and Agentic AI workflows.

---

## 🏗️ System Architecture

DevVision AI strictly separates the presentation layer from backend domain logic while maintaining a unified deployment unit:

- **Frontend**: SvelteKit, TypeScript, Tailwind CSS, shadcn-svelte architecture.
- **Backend**: Modern async Python, FastAPI, Pydantic V2, SQLAlchemy 2.0.
- **Primary Database**: PostgreSQL 16 with native `pgvector` for relational and vector state.
- **Cache & Message Broker**: Redis 7.
- **Object Storage**: S3-compatible API abstraction (MinIO locally, AWS S3/Cloudflare R2 in production).
- **Orchestration**: Docker Compose.

```
dev-vision/
├── docker/                     # Container Dockerfiles and initialization scripts
├── docs/architecture/          # Architecture Decision Records (ADRs)
├── backend/                    # FastAPI Modular Monolith
│   ├── app/
│   │   ├── api/                # Reusable dependencies (auth, csrf, rbac)
│   │   │   └── v1/             # Versioned REST endpoints (/auth, /workspaces, /documents, /health, /system)
│   │   ├── core/               # Cross-cutting: config, database, security, logging, redis, storage
│   │   ├── modules/            # Isolated domain packages
│   │   │   ├── identity/       # Users, Sessions, Argon2id, Anti-enumeration
│   │   │   ├── workspaces/     # Workspaces, Memberships, RBAC, Ownership transfer
│   │   │   └── documents/      # Validation, S3 storage, Checksums, Dedup, Cursor pagination
│   │   └── main.py             # ASGI factory, lifespan, CORS, middleware
│   ├── migrations/             # Alembic migrations (async SQLAlchemy)
│   └── tests/                  # Pytest unit & integration suite (53 tests)
├── frontend/                   # SvelteKit Application
│   ├── src/
│   │   ├── lib/                # API client with CSRF double-submit, stores, types
│   │   └── routes/             # SvelteKit pages: (auth)/login, (auth)/register, (dashboard)/app, (dashboard)/workspaces, (dashboard)/documents
│   └── static/
├── docker-compose.yml          # Complete multi-container local stack
├── .env.example                # Canonical environment template
└── README.md
```

---

## 🔐 Phase 1 Security Architecture

### 1. PostgreSQL-Backed Opaque Sessions
- **Session Tokens**: 32-byte cryptographically secure random tokens (`secrets.token_urlsafe(32)`).
- **Database Storage**: Tokens are stored strictly as SHA-256 digests (`token_hash`) in the `sessions` table. Raw tokens never enter database logs or tables.
- **Session Lifetime**: Deterministic fixed 7-day lifetime (`SESSION_MAX_AGE_SECONDS=604800`). Expired sessions are lazily purged upon access.
- **Session Transmission**: Sent exclusively via an `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` (in production) cookie named `devvision_session`. JavaScript cannot access session tokens.

### 2. Explicit Double-Submit CSRF Protection
- **CSRF Token**: 32-byte token issued in a readable cookie (`devvision_csrf`).
- **Header Injection**: SvelteKit API client automatically extracts `devvision_csrf` and injects `X-CSRF-Token` into all state-changing requests (`POST`, `PUT`, `PATCH`, `DELETE`).
- **Constant-Time Verification**: Backend verifies header token matches cookie token using `hmac.compare_digest`. Safe methods (`GET`, `HEAD`, `OPTIONS`) are exempt.

### 3. Password Security & Anti-Enumeration
- **Argon2id**: Memory-hard password hashing via `argon2-cffi` (RFC 9106 recommended parameters).
- **Password Policy**: Minimum 12 characters, maximum 128 characters. UTF-8 strings with spaces allowed; no arbitrary composition rules.
- **Login Timing Defense**: Dummy Argon2id verification executes when an email does not exist, equalizing server response latency to defend against user enumeration.
- **Registration Defense**: Generic registration responses prevent malicious enumeration of pre-registered emails.

### 4. Multi-Tenant Workspaces & RBAC
- **Tenant Boundary**: Workspaces isolate all downstream projects, documents, codebases, and configurations.
- **Roles**: `owner`, `admin`, and `member`.
- **Invariants Enforced**:
  - **Last-Owner Protection**: Sole owners cannot be deleted, demoted, or removed.
  - **Ownership Transfer**: Dedicated `POST /workspaces/{id}/transfer-ownership` atomically promotes the new owner and demotes the existing owner to `admin`.
  - **IDOR Defense**: Accessing a non-member workspace returns `404 Not Found` rather than `403 Forbidden` to prevent workspace existence enumeration.

---

## 📄 Phase 2 Document Management Architecture

### 1. Supported Document Policy & Validation
- **Supported Formats**:
  - **PDF (`.pdf`)**: Header signature verification (`%PDF-`). Structural parsing and font stream safety deferred to Phase 3. Never executed.
  - **Plain Text (`.txt`)** and **Markdown (`.md`)**: Valid UTF-8 encoding, rejection of prohibited NUL bytes (`\x00`).
  - **DOCX (`.docx`)**: Standard library `zipfile` structural audit verifying `[Content_Types].xml`, maximum 500 entries, cumulative uncompressed size <= 100 MB, compression ratio <= 10:1, rejection of encrypted entries, archive path traversal (`../`), and embedded executable binaries.
- **Hard Size Ceilings**: Maximum 20 MB ceiling for PDF and DOCX; 10 MB ceiling for TXT and Markdown.
- **Unbuffered Stream Metering**: Content-Length is checked for early rejection, but the actual consumed stream is authoritative. If stream consumption exceeds the limit, processing aborts immediately (`HTTP 413 Payload Too Large`).

### 2. Filename Security & Normalization
- Normalization strips both Unix (`/`) and Windows (`\`) slashes.
- Unicode NFKC normalization, removal of NUL bytes, ASCII controls, CR/LF, zero-width markers, and bidirectional override characters (e.g. `\u202e`).
- Multi-dot filenames (e.g. `report.v2.pdf`) are permitted based strictly on the final sanitized extension.
- Maximum display filename length is truncated to 200 characters while preserving extension.

### 3. Storage & Object Key Strategy
- **Opaque Storage Keys**: The original filename is stored strictly as metadata. The MinIO/S3 object key is server-generated:
  `workspaces/{workspace_id}/documents/{document_id}/{checksum_prefix}/{document_id}.{sanitized_ext}`
- **Private S3 Bucket**: S3 is never exposed publicly; downloads are proxied through authenticated FastAPI streaming endpoints with `X-Content-Type-Options: nosniff`.

### 4. Database-Level Duplicate Protection
- **`UNIQUE (workspace_id, checksum)` Constraint**: Prevents duplicate document contents within the same workspace at the database engine level.
- **Fast Pre-Check**: Application SELECT skips S3 network transfer if duplicate already exists.
- **Race Condition Handling**: Concurrent identical uploads trigger `IntegrityError`, roll back DB, and execute an immediate compensating S3 deletion before returning `HTTP 409 Conflict` (`DUPLICATE_DOCUMENT`).

### 5. S3-First Deletion
- Document deletion invokes `storage.delete_object(object_key)` first.
- If S3 deletion fails, the DB record is preserved and `HTTP 502 Bad Gateway` is returned, preventing ghost records.
- If S3 confirms deletion (or key is already absent), the PostgreSQL record is deleted.

### 6. Keyset Cursor Pagination
- Stable ordering: `created_at DESC, id DESC`.
- Response format: `{ "items": [...], "next_cursor": "..." }`. No expensive or drifting `total` count is computed.

---

## 🏛️ Architecture Decision Records (ADRs)

Key architectural decisions are documented under `docs/architecture/`:

1. **[ADR 0001: Modular Monolith Architecture](docs/architecture/0001-modular-monolith.md)** — Rejection of premature microservices in favor of high-velocity domain modules.
2. **[ADR 0002: SvelteKit and FastAPI Separation](docs/architecture/0002-sveltekit-fastapi-separation.md)** — High-performance Svelte reactivity coupled with Python's AI/ML ecosystem.
3. **[ADR 0003: PostgreSQL 16 + pgvector](docs/architecture/0003-postgresql-pgvector.md)** — Unified relational and high-dimensional vector embeddings without secondary vector databases.
4. **[ADR 0004: S3-Compatible Object Storage](docs/architecture/0004-s3-compatible-object-storage.md)** — Decoupled binary storage using MinIO locally and AWS S3 in production.

---

## 🚀 Getting Started

### Prerequisites

- **Node.js** (v20+) and **npm** (v10+)
- **Python** (v3.11+) or `uv`
- **Docker** and **Docker Compose** (optional for bare-metal, recommended for full stack)

---

### Option A: Running via Docker Compose (Recommended)

1. Clone the repository and navigate to root:
   ```bash
   git clone https://github.com/Eshwar187/dev_vision.git
   cd dev_vision
   ```

2. Copy the environment configuration:
   ```bash
   cp .env.example .env
   ```

3. Build and launch all services:
   ```bash
   docker compose up --build
   ```

4. Verify services:
   - **SvelteKit Frontend**: http://localhost:5173
   - **FastAPI API & Docs**: http://localhost:8000/docs
   - **MinIO Console**: http://localhost:9001 (User: `minioadmin`, Pass: `minioadmin`)
   - **PostgreSQL**: `localhost:5432` (DB: `devvision`, User: `devvision`)
   - **Redis**: `localhost:6379`

---

### Option B: Running Bare-Metal / Local Development

#### 1. Backend Setup

```bash
cd backend

# Create virtual environment with uv
uv venv --python 3.11 .venv

# Activate virtual environment (Windows PowerShell)
.\.venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Run backend server
uvicorn app.main:app --reload --port 8000
```

#### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run Vite development server
npm run dev -- --port 5173
```

---

## 🧪 Testing & Verification

### Run Backend Test Suite
```bash
# Run all unit and integration tests from repository root
backend\.venv\Scripts\pytest.exe backend/tests -v
```

### Run Frontend Typecheck & Build
```bash
cd frontend
npm run check
npm run build
```

---

## 🛡️ API Endpoints Summary

### Authentication (`/api/v1/auth`)
- `POST /register`: Register user and create default personal workspace.
- `POST /login`: Verify credentials, issue `devvision_session` and `devvision_csrf` cookies.
- `POST /logout`: Revoke session in database, clear cookies.
- `GET /me`: Return authenticated user profile.

### Workspaces (`/api/v1/workspaces`)
- `POST /`: Create workspace and assign creator as `owner`.
- `GET /`: List all workspaces the current user is a member of.
- `GET /{id}`: Retrieve workspace details and member count.
- `PATCH /{id}`: Update workspace name (`admin` or `owner`).
- `DELETE /{id}`: Delete workspace (`owner` only; cascade deletes memberships).
- `GET /{id}/members`: List all workspace members and their roles.
- `POST /{id}/members`: Add registered user by email (`admin` or `owner`).
- `PATCH /{id}/members/{user_id}`: Update member role (`owner` only).
- `DELETE /{id}/members/{user_id}`: Remove member or leave workspace.
- `POST /{id}/transfer-ownership`: Transfer sole workspace ownership to another member (`owner` only).

### Documents (`/api/v1/workspaces/{workspace_id}/documents`)
- `POST /`: Upload document with size metering, signature inspection, SHA-256 deduplication, and S3-first compensating rollback.
- `GET /`: List workspace documents with stable keyset cursor pagination (`created_at DESC, id DESC`).
- `GET /{id}`: Retrieve document metadata.
- `GET /{id}/download`: Stream binary document file from S3 through authenticated FastAPI proxy.
- `DELETE /{id}`: Delete document using S3-first deletion flow and RBAC rules (owner/admin deletes any, member deletes own).

### Diagnostics & Probes
- `GET /health/live`: Shallow liveness probe.
- `GET /health/ready`: Deep readiness probe checking PostgreSQL, pgvector, Redis, and MinIO connectivity.
- `GET /api/v1/system/info`: Current runtime metadata and API version.
