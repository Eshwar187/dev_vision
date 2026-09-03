# ADR 0002: SvelteKit and FastAPI Decoupled Separation

## Status
Accepted

## Context
DevVision AI requires high-performance user interaction, real-time streaming tokens (Server-Sent Events), and interactive dashboards. Meanwhile, the backend requires deep integration with Python's AI/ML ecosystem (PyTorch, OpenCV, LangGraph, Whisper, Hugging Face).

Unified full-stack JavaScript frameworks (like Next.js) cannot natively run Python machine learning workloads without bridging to Python subprocesses or secondary services. Conversely, Python web template engines (like Jinja2) lack the reactive, rich client capabilities needed for modern developer tooling.

## Decision
We enforce a strict separation between:
1. **Frontend**: SvelteKit with TypeScript, Tailwind CSS, and shadcn-svelte primitives.
2. **Backend**: FastAPI with modern async Python and Pydantic.
3. **Contract**: Formal API contracts versioned at `/api/v1` and documented automatically via OpenAPI 3.1.

## Consequences
- **Positive**:
  - Frontend developers benefit from Svelte 5's lightweight reactivity, ultra-fast compile times, and clean component state without virtual DOM overhead.
  - Backend leverages Python's native AI/ML libraries and FastAPI's high-throughput async ASGI event loop.
  - The frontend can be hosted as an independent static SPA or lightweight Node server, while the backend scales independently.
- **Negative / Tradeoffs**:
  - Two language ecosystems (Node.js/TypeScript and Python) requiring separate dependency managers (`npm` and `py`/`uv`).
  - Need for automated type synchronization from FastAPI's OpenAPI schema to TypeScript interfaces.
