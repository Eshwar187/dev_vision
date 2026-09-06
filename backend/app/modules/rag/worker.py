"""
DevVision AI - Document Ingestion Worker & Background Indexing Engine.

Handles:
- Acquisition & renewal of document_processing_leases with fencing tokens.
- Transactional ownership barriers for worker mutations:
    SELECT ... FROM document_processing_leases WHERE document_id = :id FOR UPDATE
    ensuring stale workers cannot commit if another worker reclaimed the lease.
- Extraction (PDF, DOCX, TXT/MD), token-aware chunking, dense embedding generation,
  and batch insertion (50 chunks per batch) with search_vector tsvector generation.
- Zero-downtime generation activation via document row lock (SELECT ... FOR UPDATE on documents)
  serializing activation with retired-generation GC.
- Retired generation GC with 1-hour grace period.
"""

import asyncio
import io
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import structlog
from sqlalchemy import select, update, delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.storage import get_storage
from app.modules.documents.models import Document
from app.modules.rag.models import (
    DocumentIndexGeneration,
    DocumentProcessingLease,
    DocumentChunk,
)
from app.modules.rag.protocols import EmbeddingModel
from app.modules.rag.extractors import extract_document
from app.modules.rag.chunking import RecursiveStructuralChunker
from app.modules.rag.embeddings import BgeEmbeddingModel

logger = structlog.get_logger(__name__)


class IngestionWorker:
    """
    Worker orchestrating document indexing with strict fencing and transactional safety.
    """

    def __init__(
        self,
        worker_id: Optional[str] = None,
        embedding_model: Optional[EmbeddingModel] = None,
    ):
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.embedding_model = embedding_model or BgeEmbeddingModel()
        self.chunker = RecursiveStructuralChunker()
        self.settings = get_settings()

    async def acquire_lease(
        self, db: AsyncSession, document_id: uuid.UUID
    ) -> Optional[int]:
        """
        Acquire or reclaim an expired lease on the document.
        Returns the new fencing_token if acquired, or None if already actively leased.
        """
        now = datetime.now(timezone.utc)
        lease_duration = timedelta(seconds=self.settings.RAG_PROCESSING_LEASE_SECONDS)
        lease_expires_at = now + lease_duration

        # Fetch current lease record with row lock
        stmt = (
            select(DocumentProcessingLease)
            .where(DocumentProcessingLease.document_id == document_id)
            .with_for_update()
        )
        res = await db.execute(stmt)
        lease = res.scalar_one_or_none()

        if lease is None:
            # First lease on document
            token = 1
            new_lease = DocumentProcessingLease(
                document_id=document_id,
                worker_id=self.worker_id,
                fencing_token=token,
                lease_acquired_at=now,
                lease_expires_at=lease_expires_at,
                heartbeat_at=now,
            )
            db.add(new_lease)
            await db.commit()
            return token

        # If existing lease is not expired and owned by someone else, cannot acquire
        expires_at = lease.lease_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at > now and lease.worker_id != self.worker_id:
            await db.rollback()
            return None

        # Reclaim or renew: increment fencing token monotonically
        token = lease.fencing_token + 1
        lease.worker_id = self.worker_id
        lease.fencing_token = token
        lease.lease_acquired_at = now
        lease.lease_expires_at = lease_expires_at
        lease.heartbeat_at = now
        await db.commit()
        return token

    async def heartbeat(
        self, db: AsyncSession, document_id: uuid.UUID, fencing_token: int
    ) -> bool:
        """
        Extend lease duration if still held with matching fencing token.
        """
        now = datetime.now(timezone.utc)
        new_expires = now + timedelta(seconds=self.settings.RAG_PROCESSING_LEASE_SECONDS)

        stmt = (
            update(DocumentProcessingLease)
            .where(
                DocumentProcessingLease.document_id == document_id,
                DocumentProcessingLease.worker_id == self.worker_id,
                DocumentProcessingLease.fencing_token == fencing_token,
            )
            .values(heartbeat_at=now, lease_expires_at=new_expires)
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0

    async def verify_fencing_ownership_barrier(
        self, db: AsyncSession, document_id: uuid.UUID, fencing_token: int
    ) -> None:
        """
        Transactional ownership barrier.
        Locks the lease row and asserts this worker holds the matching fencing token.
        Raises RuntimeError if lease was lost or reclaimed by another worker.
        """
        stmt = (
            select(DocumentProcessingLease)
            .where(
                DocumentProcessingLease.document_id == document_id,
                DocumentProcessingLease.worker_id == self.worker_id,
                DocumentProcessingLease.fencing_token == fencing_token,
            )
            .with_for_update()
        )
        res = await db.execute(stmt)
        lease = res.scalar_one_or_none()
        if lease is None:
            raise RuntimeError(
                f"Fencing ownership barrier violation: worker {self.worker_id} with token {fencing_token} "
                f"no longer owns document {document_id}."
            )

    async def release_lease(
        self, db: AsyncSession, document_id: uuid.UUID, fencing_token: int
    ) -> None:
        """Clean up lease upon completion."""
        stmt = delete(DocumentProcessingLease).where(
            DocumentProcessingLease.document_id == document_id,
            DocumentProcessingLease.worker_id == self.worker_id,
            DocumentProcessingLease.fencing_token == fencing_token,
        )
        await db.execute(stmt)
        await db.commit()

    async def index_document(
        self,
        document_id: uuid.UUID,
        trigger_reason: str = "initial_upload",
    ) -> uuid.UUID:
        """
        Execute full indexing lifecycle for a document in a background worker session.
        """
        async with AsyncSessionLocal() as db:
            fencing_token = await self.acquire_lease(db, document_id)
            if fencing_token is None:
                raise RuntimeError(f"Document {document_id} is currently leased by another active worker.")

        heartbeat_task: Optional[asyncio.Task] = None
        stop_heartbeat = asyncio.Event()

        async def _heartbeat_loop():
            interval = self.settings.RAG_PROCESSING_HEARTBEAT_SECONDS
            while not stop_heartbeat.is_set():
                try:
                    await asyncio.sleep(interval)
                    async with AsyncSessionLocal() as h_db:
                        ok = await self.heartbeat(h_db, document_id, fencing_token)
                        if not ok:
                            logger.error(
                                "lost_processing_lease_heartbeat",
                                document_id=str(document_id),
                                worker_id=self.worker_id,
                                token=fencing_token,
                            )
                            break
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.warning("heartbeat_exception", error=str(exc))

        heartbeat_task = asyncio.create_task(_heartbeat_loop())

        try:
            # 1. Fetch document metadata and create new generation
            async with AsyncSessionLocal() as db:
                await self.verify_fencing_ownership_barrier(db, document_id, fencing_token)
                
                doc = await db.get(Document, document_id)
                if not doc:
                    raise ValueError(f"Document {document_id} not found")

                # Count existing generations for version numbering
                count_stmt = select(DocumentIndexGeneration).where(
                    DocumentIndexGeneration.document_id == document_id
                )
                existing_gens = (await db.execute(count_stmt)).scalars().all()
                gen_version = len(existing_gens) + 1

                generation = DocumentIndexGeneration(
                    document_id=document_id,
                    version=gen_version,
                    stage="extracting",
                    status="building",
                    trigger_reason=trigger_reason,
                    embedding_model=self.embedding_model.model_name,
                    embedding_version=self.embedding_model.model_version,
                    embedding_dimension=self.embedding_model.dimension,
                )
                db.add(generation)

                # Set macro status to processing
                doc.status = "processing"
                doc.status_message = f"Building index generation v{gen_version} (extracting)..."
                await db.commit()
                await db.refresh(generation)
                gen_id = generation.id
                storage_path = doc.storage_path
                doc_name = doc.name

            # 2. Download file content from object storage
            storage = get_storage()
            file_bytes = await asyncio.to_thread(storage.get_object_bytes, storage_path)

            # 3. Extract text content
            extraction_result = extract_document(file_bytes, doc_name)

            async with AsyncSessionLocal() as db:
                await self.verify_fencing_ownership_barrier(db, document_id, fencing_token)
                gen = await db.get(DocumentIndexGeneration, gen_id)
                if gen:
                    gen.stage = "chunking"
                    gen.unextractable_pages = extraction_result.unextractable_pages
                doc = await db.get(Document, document_id)
                if doc:
                    doc.status_message = f"Building index generation v{gen_version} (chunking)..."
                await db.commit()

            # 4. Chunk sections into deterministic passages
            tokenized_chunks = self.chunker.chunk_document(
                extraction_result.sections,
                target_tokens=500,
                overlap_tokens=50,
            )

            async with AsyncSessionLocal() as db:
                await self.verify_fencing_ownership_barrier(db, document_id, fencing_token)
                gen = await db.get(DocumentIndexGeneration, gen_id)
                if gen:
                    gen.stage = "embedding"
                    gen.total_chunks = len(tokenized_chunks)
                doc = await db.get(Document, document_id)
                if doc:
                    doc.status_message = f"Building index generation v{gen_version} (embedding {len(tokenized_chunks)} chunks)..."
                await db.commit()

            # 5. Embed in batches of 50 and persist to document_chunks
            batch_size = 50
            for i in range(0, len(tokenized_chunks), batch_size):
                batch = tokenized_chunks[i : i + batch_size]
                batch_texts = [c.content for c in batch]
                batch_embeddings = await self.embedding_model.embed_texts(batch_texts)

                async with AsyncSessionLocal() as db:
                    # Transactional ownership barrier before mutating database
                    await self.verify_fencing_ownership_barrier(db, document_id, fencing_token)

                    for chunk_idx, (chunk_data, emb) in enumerate(
                        zip(batch, batch_embeddings), start=i
                    ):
                        vector_str = f"[{','.join(str(round(v, 6)) for v in emb)}]"
                        # Insert chunk with raw vector literal and tsvector search_vector
                        insert_chunk_sql = text("""
                            INSERT INTO document_chunks (
                                id, document_id, generation_id, chunk_index,
                                content, page_number, section_heading,
                                token_count, embedding, search_vector, created_at
                            ) VALUES (
                                :id, :document_id, :generation_id, :chunk_index,
                                :content, :page_number, :section_heading,
                                :token_count, cast(:embedding as vector),
                                to_tsvector('english', :content), NOW()
                            )
                        """)
                        await db.execute(
                            insert_chunk_sql,
                            {
                                "id": uuid.uuid4(),
                                "document_id": document_id,
                                "generation_id": gen_id,
                                "chunk_index": chunk_idx,
                                "content": chunk_data.content,
                                "page_number": chunk_data.page_number,
                                "section_heading": chunk_data.section_heading,
                                "token_count": chunk_data.token_count,
                                "embedding": vector_str,
                            },
                        )

                    gen = await db.get(DocumentIndexGeneration, gen_id)
                    if gen:
                        gen.embedded_chunks = min(i + len(batch), len(tokenized_chunks))
                    await db.commit()

            # 6. Zero-Downtime Activation & Retired-Generation Retirement
            async with AsyncSessionLocal() as db:
                # Row lock on document to serialize activation with retired generation GC
                doc_stmt = (
                    select(Document)
                    .where(Document.id == document_id)
                    .with_for_update()
                )
                doc_res = await db.execute(doc_stmt)
                doc = doc_res.scalar_one()

                # Verify ownership barrier
                await self.verify_fencing_ownership_barrier(db, document_id, fencing_token)

                now = datetime.now(timezone.utc)
                prev_active_id = doc.active_generation_id

                # If there was a previous active generation, retire it
                if prev_active_id:
                    retire_stmt = (
                        update(DocumentIndexGeneration)
                        .where(DocumentIndexGeneration.id == prev_active_id)
                        .values(status="retired", retired_at=now)
                    )
                    await db.execute(retire_stmt)

                # Mark new generation as active
                gen_stmt = (
                    update(DocumentIndexGeneration)
                    .where(DocumentIndexGeneration.id == gen_id)
                    .values(
                        status="active",
                        stage="ready",
                        activated_at=now,
                        embedded_chunks=len(tokenized_chunks),
                    )
                )
                await db.execute(gen_stmt)

                # Set document active generation and ready status
                doc.active_generation_id = gen_id
                doc.status = "ready"
                doc.status_message = "Document indexed and ready for retrieval."
                await db.commit()

            logger.info(
                "document_indexed_successfully",
                document_id=str(document_id),
                generation_id=str(gen_id),
                chunks=len(tokenized_chunks),
            )
            return gen_id

        except Exception as exc:
            logger.error("document_indexing_failed", document_id=str(document_id), error=str(exc))
            # Mark generation and document as failed
            try:
                async with AsyncSessionLocal() as db:
                    gen = await db.get(DocumentIndexGeneration, gen_id)
                    if gen:
                        gen.status = "failed"
                        gen.error_message = str(exc)
                    doc = await db.get(Document, document_id)
                    if doc:
                        doc.status = "failed"
                        doc.status_message = f"Indexing failed: {str(exc)}"
                    await db.commit()
            except Exception:
                pass
            raise

        finally:
            # Stop heartbeat and release lease
            stop_heartbeat.set()
            if heartbeat_task:
                heartbeat_task.cancel()
            try:
                async with AsyncSessionLocal() as db:
                    await self.release_lease(db, document_id, fencing_token)
            except Exception as exc:
                logger.warning("lease_release_failed", error=str(exc))

    async def cleanup_retired_generations(
        self, db: AsyncSession, grace_period_hours: int = 1
    ) -> int:
        """
        Safely delete retired generations older than grace period (default 1 hour).
        Row-locks documents to guarantee serialized, race-free GC.
        """
        threshold = datetime.now(timezone.utc) - timedelta(hours=grace_period_hours)
        
        # Find candidate retired generations older than threshold
        find_stmt = select(DocumentIndexGeneration).where(
            DocumentIndexGeneration.status == "retired",
            DocumentIndexGeneration.retired_at < threshold,
        )
        res = await db.execute(find_stmt)
        candidates = res.scalars().all()

        deleted_count = 0
        for gen in candidates:
            # Lock the parent document row
            doc_stmt = (
                select(Document)
                .where(Document.id == gen.document_id)
                .with_for_update()
            )
            doc_res = await db.execute(doc_stmt)
            doc = doc_res.scalar_one_or_none()

            # Verify it is still NOT the active generation
            if doc and doc.active_generation_id != gen.id:
                # Delete chunks belonging to this retired generation
                del_chunks = delete(DocumentChunk).where(DocumentChunk.generation_id == gen.id)
                await db.execute(del_chunks)
                # Delete the generation record
                del_gen = delete(DocumentIndexGeneration).where(DocumentIndexGeneration.id == gen.id)
                await db.execute(del_gen)
                await db.commit()
                deleted_count += 1
            else:
                await db.rollback()

        return deleted_count
