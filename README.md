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
│   │   ├── api/v1/             # Versioned REST endpoints (/health, /system)
│   │   ├── core/               # Cross-cutting: config, database, logging, redis, storage
│   │   ├── modules/            # Isolated domain packages
│   │   └── main.py             # ASGI factory, lifespan, CORS, middleware
│   ├── migrations/             # Alembic migrations (async SQLAlchemy)
│   └── tests/                  # Pytest unit & integration suite
├── frontend/                   # SvelteKit Application
│   ├── src/
│   │   ├── lib/                # API client, components, utilities
│   │   └── routes/             # SvelteKit pages and layouts
│   └── static/
├── docker-compose.yml          # Complete multi-container local stack
├── .env.example                # Canonical environment template
└── README.md
```

---

## 🏛️ Architecture Decision Records (ADRs)

Key Phase 0 architectural decisions are documented under `docs/architecture/`:

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

# Create virtual environment
uv venv --python 3.11 .venv

# Activate virtual environment (Windows PowerShell)
.venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt

# Run backend server
python -m uvicorn app.main:app --reload --port 8000
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
# From repository root
backend\.venv\Scripts\pytest.exe backend/tests -v
```

### Run Frontend Typecheck & Build
```bash
cd frontend
npm run check
npm run build
```

---

## 🛡️ Health Endpoints

- `GET /health/live`: Shallow liveness probe returning process status and correlation ID.
- `GET /health/ready`: Deep readiness probe checking PostgreSQL, pgvector, Redis, and MinIO connectivity.
- `GET /api/v1/system/info`: Metadata about current runtime, version, and environment.