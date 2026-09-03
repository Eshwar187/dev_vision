# ADR 0001: Modular Monolith Architecture

## Status
Accepted

## Context
DevVision AI is an ambitious multimodal developer copilot requiring document RAG, codebase intelligence, GitHub PR automation, computer vision, voice, and agentic workflows. As an early-stage production-oriented product developed by a solo developer, choosing between microservices and a monolith is a critical architectural pivot point.

Microservices introduce significant operational complexity: distributed transactions, network latency, multiple CI/CD pipelines, complex local orchestration, distributed tracing, and service mesh management. These overheads are detrimental to iteration speed and developer ergonomics.

## Decision
We adopt a **modular monolith** architectural pattern.
- All core application domains (identity, documents, jobs, health, future agent workflows) reside within a single codebase and deployment unit.
- Domain boundaries are strictly enforced via modular Python packages (`backend/app/modules/<domain>`).
- Cross-module communication happens through clean Python interfaces/services rather than internal HTTP or RPC hops.
- Asynchronous tasks and long-running compute operations are decoupled via a shared Redis message broker, ready to be offloaded to worker processes without breaking the monolith.

## Consequences
- **Positive**:
  - Single repository, zero distributed deployment overhead, instant local onboarding.
  - ACID transactions across domain tables within PostgreSQL.
  - Clean evolution path: individual modules can later be extracted into standalone services if and only if team size or specific scaling bottlenecks demand it.
- **Negative / Tradeoffs**:
  - Requires developer discipline to maintain strict module boundaries and prevent spaghetti dependency coupling.
