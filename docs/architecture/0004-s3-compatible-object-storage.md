# ADR 0004: S3-Compatible Object Storage with MinIO for Local Development

## Status
Accepted

## Context
DevVision AI handles unstructured artifacts including user-uploaded documents (PDFs, Markdown, repositories), OCR intermediate frames, audio clips, and AI review diffs.

Storing binary files directly in PostgreSQL (as `BYTEA`) inflates database size and complicates backups. Storing files directly on the local server file system prevents horizontal multi-instance scaling.

## Decision
We use an **S3-compatible Object Storage abstraction**.
- Local development uses **MinIO** running in Docker, exposing standard S3 API endpoints.
- Production environments can swap MinIO for AWS S3, Cloudflare R2, or Wasabi with zero application code changes, merely changing environment variables (`S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, etc.).
- The backend accesses storage strictly through a decoupled `StorageService` interface.
- Phase 0 uses a single private bucket (`devvision-local`).

## Consequences
- **Positive**:
  - Standardized S3 API ensures cloud portability and multi-cloud readiness.
  - Unstructured files are decoupled from application and database instances.
  - Enables secure direct upload/download via presigned URLs in future phases.
- **Negative / Tradeoffs**:
  - Requires MinIO container running during local development.
