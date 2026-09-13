"""
DevVision AI - Standalone RAG Ingestion Worker Daemon.

Provides:
- Continuous polling for pending or lease-expired documents.
- Distributed worker fencing and zero-downtime generation activation.
- Graceful SIGTERM / SIGINT shutdown ensuring no active generation corruption.
- Periodic garbage collection of retired and failed generations.
"""

import asyncio
import os
import signal
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import and_, or_, select
import structlog

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import setup_logging
from app.core.metrics import (
    rag_documents_ingested_total,
    rag_generation_gc_total,
    rag_ingestion_duration_seconds,
    rag_ingestion_failures_total,
)
from app.modules.documents.models import Document
from app.modules.rag.models import DocumentProcessingLease
from app.modules.rag.worker import IngestionWorker

logger = structlog.get_logger("worker.daemon")


class WorkerDaemon:
    """Production worker daemon managing asynchronous indexing jobs and lifecycle events."""

    def __init__(self, worker_id: Optional[str] = None, poll_interval_seconds: float = 5.0):
        self.worker_id = worker_id or f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.poll_interval = poll_interval_seconds
        self.worker = IngestionWorker(worker_id=self.worker_id)
        self.settings = get_settings()
        self.is_running = False
        self._stop_event = asyncio.Event()
        self._last_gc_run = datetime.now(timezone.utc)

    def stop(self, *args):
        """Signals the worker loop to stop gracefully after current unit of work."""
        logger.info("worker_shutdown_signal_received", worker_id=self.worker_id)
        self.is_running = False
        self._stop_event.set()

    async def run(self):
        """Main daemon loop."""
        self.is_running = True
        logger.info(
            "worker_daemon_started",
            worker_id=self.worker_id,
            poll_interval=self.poll_interval,
            embedding_model=self.settings.EMBEDDING_MODEL_NAME,
        )

        while self.is_running and not self._stop_event.is_set():
            try:
                # 1. Process candidate pending documents
                await self._process_pending_documents()

                # 2. Periodic Garbage Collection of retired generations (every 10 minutes)
                now = datetime.now(timezone.utc)
                if (now - self._last_gc_run).total_seconds() > 600:
                    await self._run_garbage_collection()
                    self._last_gc_run = now

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("worker_daemon_loop_error", worker_id=self.worker_id, error=str(exc))

            # Bounded sleep checking stop event
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                pass

        logger.info("worker_daemon_stopped_gracefully", worker_id=self.worker_id)

    async def _process_pending_documents(self):
        """Finds documents that need indexing and processes them with fencing protection."""
        now = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as db:
            # Documents needing indexing:
            # 1. status == 'pending'
            # 2. status == 'processing' but lease expired (worker crash recovery)
            active_leases_subq = (
                select(DocumentProcessingLease.document_id)
                .where(DocumentProcessingLease.expires_at > now)
            )

            stmt = (
                select(Document.id)
                .where(
                    or_(
                        Document.status == "pending",
                        and_(
                            Document.status == "processing",
                            Document.id.not_in(active_leases_subq),
                        ),
                    )
                )
                .order_by(Document.created_at.asc())
                .limit(self.settings.MAX_CONCURRENT_INGESTION_JOBS)
            )
            res = await db.execute(stmt)
            candidate_ids = res.scalars().all()

        for doc_id in candidate_ids:
            if self._stop_event.is_set():
                break
            try:
                logger.info("worker_processing_candidate", document_id=str(doc_id), worker_id=self.worker_id)
                t0 = datetime.now(timezone.utc)
                await self.worker.index_document(doc_id, trigger_reason="daemon_poll")
                elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
                rag_ingestion_duration_seconds.observe(elapsed)
                rag_documents_ingested_total.inc(status="success")
            except RuntimeError as rerr:
                # Normal condition: lease held by another worker
                logger.debug("worker_lease_held_by_peer", document_id=str(doc_id), message=str(rerr))
            except Exception as exc:
                rag_documents_ingested_total.inc(status="failure")
                rag_ingestion_failures_total.inc(stage="execution")
                logger.error("worker_document_indexing_failed", document_id=str(doc_id), error=str(exc))

    async def _run_garbage_collection(self):
        """Safely purges retired generations older than 1 hour."""
        try:
            async with AsyncSessionLocal() as db:
                deleted = await self.worker.cleanup_retired_generations(db, grace_period_hours=1)
                if deleted > 0:
                    rag_generation_gc_total.inc(deleted)
                    logger.info("worker_gc_completed", deleted_generations=deleted)
        except Exception as exc:
            logger.warning("worker_gc_failed", error=str(exc))


def main():
    setup_logging()
    daemon = WorkerDaemon()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Register OS termination signals
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, daemon.stop)
        except (NotImplementedError, AttributeError):
            # Windows signal handling fallback
            signal.signal(sig, daemon.stop)

    try:
        loop.run_until_complete(daemon.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
