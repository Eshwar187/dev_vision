"""
DevVision AI - Hybrid Retrieval Engine & Reciprocal Rank Fusion.

Combines dense semantic search (pgvector cosine similarity) with sparse lexical
search (PostgreSQL full-text search tsvector) scoped strictly to workspace_id
and active document generations.

Exact mathematical RRF Formula:
    RRF(d) = I(d in dense)/(60 + rank_dense(d)) + I(d in sparse)/(60 + rank_sparse(d))
    where k = 60, ranks are 1-indexed, absent candidates contribute 0.

Deterministic Tie-Breaking:
    ORDER BY rrf_score DESC, rank_dense ASC NULLS LAST, rank_sparse ASC NULLS LAST, chunk_id ASC
"""

import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from sqlalchemy import select, literal, text
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import get_settings
from app.core.metrics import (
    rag_dense_retrieval_duration_seconds,
    rag_rerank_duration_seconds,
    rag_sparse_retrieval_duration_seconds,
)
from app.modules.rag.protocols import EmbeddingModel, RerankerModel

logger = structlog.get_logger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    generation_id: uuid.UUID
    document_name: str
    chunk_index: int
    content: str
    page_number: Optional[int]
    section_heading: Optional[str]
    token_count: int
    dense_rank: Optional[int]
    sparse_rank: Optional[int]
    dense_similarity: Optional[float]
    sparse_rank_score: Optional[float]
    rrf_score: float
    rerank_score: Optional[float] = None
    citation_marker: Optional[int] = None


class HybridRetrievalService:
    """
    Executes dense and sparse candidate retrieval, calculates Reciprocal Rank Fusion,
    and applies optional cross-encoder reranking.
    """

    def __init__(
        self,
        embedding_model: EmbeddingModel,
        reranker_model: Optional[RerankerModel] = None,
        k: int = 60,
    ):
        self.embedding_model = embedding_model
        self.reranker_model = reranker_model
        self.k = k  # RRF smoothing constant

    async def retrieve(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        query: str,
        limit_dense: int = 20,
        limit_sparse: int = 20,
        top_k: int = 5,
        apply_reranker: bool = True,
    ) -> List[RetrievedChunk]:
        """
        Execute hybrid retrieval for a given workspace query.
        Scoped exclusively to documents in the specified workspace whose status is 'ready'
        and chunks belong to the active_generation_id of the document.
        """
        from app.modules.documents.models import Document
        from app.modules.rag.models import DocumentChunk

        # 1. Point-in-time active generation snapshot for ready documents in workspace
        active_docs_stmt = (
            select(Document.id, Document.active_generation_id)
            .where(
                Document.workspace_id == workspace_id,
                Document.status == "ready",
                Document.active_generation_id.isnot(None),
            )
        )
        active_pairs = (await db.execute(active_docs_stmt)).all()
        if not active_pairs:
            return []

        active_gen_ids = [gen_id for _, gen_id in active_pairs if gen_id is not None]
        if not active_gen_ids:
            return []

        # 2. Compute query embedding for dense search
        query_vector = await self.embedding_model.embed_query(query)
        vector_str = f"[{','.join(str(round(v, 6)) for v in query_vector)}]"

        # 3. Dense & Sparse candidate search pinned strictly to active_gen_ids snapshot
        dialect_name = db.bind.dialect.name if db.bind else "postgresql"

        t_dense = time.perf_counter()
        if dialect_name == "sqlite":
            stmt_dense = (
                select(
                    DocumentChunk.id.label("chunk_id"),
                    DocumentChunk.document_id,
                    DocumentChunk.generation_id,
                    Document.original_filename.label("document_name"),
                    DocumentChunk.chunk_index,
                    DocumentChunk.text_content.label("content"),
                    DocumentChunk.page_number,
                    DocumentChunk.section_heading,
                    DocumentChunk.token_count,
                    literal(1.0).label("dense_score"),
                )
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(
                    DocumentChunk.workspace_id == workspace_id,
                    Document.workspace_id == workspace_id,
                    Document.status == "ready",
                    DocumentChunk.generation_id.in_(active_gen_ids),
                    Document.active_generation_id == DocumentChunk.generation_id,
                )
                .limit(limit_dense)
            )
            dense_rows = (await db.execute(stmt_dense)).mappings().all()
            rag_dense_retrieval_duration_seconds.observe(time.perf_counter() - t_dense)

            t_sparse = time.perf_counter()
            stmt_sparse = (
                select(
                    DocumentChunk.id.label("chunk_id"),
                    DocumentChunk.document_id,
                    DocumentChunk.generation_id,
                    Document.original_filename.label("document_name"),
                    DocumentChunk.chunk_index,
                    DocumentChunk.text_content.label("content"),
                    DocumentChunk.page_number,
                    DocumentChunk.section_heading,
                    DocumentChunk.token_count,
                    literal(1.0).label("sparse_score"),
                )
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(
                    DocumentChunk.workspace_id == workspace_id,
                    Document.workspace_id == workspace_id,
                    Document.status == "ready",
                    DocumentChunk.generation_id.in_(active_gen_ids),
                    Document.active_generation_id == DocumentChunk.generation_id,
                )
                .limit(limit_sparse)
            )
            sparse_rows = (await db.execute(stmt_sparse)).mappings().all()
            rag_sparse_retrieval_duration_seconds.observe(time.perf_counter() - t_sparse)
        else:
            # PostgreSQL + pgvector query
            # Increase HNSW ef_search for transactional query to avoid recall exhaustion under filtered workspaces
            try:
                await db.execute(text("SET LOCAL hnsw.ef_search = 100;"))
            except Exception:
                pass

            dense_sql = text("""
                SELECT 
                    c.id AS chunk_id,
                    c.document_id,
                    c.generation_id,
                    d.original_filename AS document_name,
                    c.chunk_index,
                    c.text_content AS content,
                    c.page_number,
                    c.section_heading,
                    c.token_count,
                    (1 - (c.embedding <=> cast(:query_vector as vector))) AS dense_score
                FROM document_chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.workspace_id = :workspace_id
                  AND d.workspace_id = :workspace_id
                  AND d.status = 'ready'
                  AND c.generation_id = ANY(:active_gen_ids)
                  AND d.active_generation_id = c.generation_id
                  AND c.embedding IS NOT NULL
                ORDER BY c.embedding <=> cast(:query_vector as vector) ASC
                LIMIT :limit_dense
            """)
            dense_rows = (await db.execute(
                dense_sql,
                {
                    "query_vector": vector_str,
                    "workspace_id": workspace_id,
                    "active_gen_ids": active_gen_ids,
                    "limit_dense": limit_dense,
                },
            )).mappings().all()
            rag_dense_retrieval_duration_seconds.observe(time.perf_counter() - t_dense)

            t_sparse = time.perf_counter()
            sparse_sql = text("""
                SELECT 
                    c.id AS chunk_id,
                    c.document_id,
                    c.generation_id,
                    d.original_filename AS document_name,
                    c.chunk_index,
                    c.text_content AS content,
                    c.page_number,
                    c.section_heading,
                    c.token_count,
                    ts_rank(c.tsv_content, plainto_tsquery('english', :query)) AS sparse_score
                FROM document_chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.workspace_id = :workspace_id
                  AND d.workspace_id = :workspace_id
                  AND d.status = 'ready'
                  AND c.generation_id = ANY(:active_gen_ids)
                  AND d.active_generation_id = c.generation_id
                  AND c.tsv_content @@ plainto_tsquery('english', :query)
                ORDER BY sparse_score DESC
                LIMIT :limit_sparse
            """)
            sparse_rows = (await db.execute(
                sparse_sql,
                {
                    "query": query,
                    "workspace_id": workspace_id,
                    "active_gen_ids": active_gen_ids,
                    "limit_sparse": limit_sparse,
                },
            )).mappings().all()
            rag_sparse_retrieval_duration_seconds.observe(time.perf_counter() - t_sparse)

        # 4. Compute 1-indexed ranks
        # dense_ranks: chunk_id -> (rank_1_indexed, similarity, row_data)
        dense_map: Dict[uuid.UUID, Tuple[int, float, dict]] = {}
        for rank_idx, row in enumerate(dense_rows, start=1):
            dense_map[row["chunk_id"]] = (rank_idx, float(row["dense_score"]), dict(row))

        # sparse_ranks: chunk_id -> (rank_1_indexed, score, row_data)
        sparse_map: Dict[uuid.UUID, Tuple[int, float, dict]] = {}
        for rank_idx, row in enumerate(sparse_rows, start=1):
            sparse_map[row["chunk_id"]] = (rank_idx, float(row["sparse_score"]), dict(row))

        # 5. Exact Reciprocal Rank Fusion calculation with deterministic candidate set ordering
        # RRF(d) = I(d in dense)/(60 + rank_dense(d)) + I(d in sparse)/(60 + rank_sparse(d))
        all_chunk_ids = sorted(set(dense_map.keys()).union(set(sparse_map.keys())), key=str)
        candidates: List[RetrievedChunk] = []

        for cid in all_chunk_ids:
            dense_info = dense_map.get(cid)
            sparse_info = sparse_map.get(cid)

            dense_rank = dense_info[0] if dense_info else None
            dense_score = dense_info[1] if dense_info else None
            
            sparse_rank = sparse_info[0] if sparse_info else None
            sparse_score = sparse_info[1] if sparse_info else None

            # Base metadata row from whichever retrieved it
            row_data = dense_info[2] if dense_info else sparse_info[2]  # type: ignore

            rrf = 0.0
            if dense_rank is not None:
                rrf += 1.0 / (self.k + dense_rank)
            if sparse_rank is not None:
                rrf += 1.0 / (self.k + sparse_rank)

            candidates.append(
                RetrievedChunk(
                    chunk_id=cid,
                    document_id=row_data["document_id"],
                    generation_id=row_data["generation_id"],
                    document_name=row_data["document_name"],
                    chunk_index=row_data["chunk_index"],
                    content=row_data["content"],
                    page_number=row_data["page_number"],
                    section_heading=row_data["section_heading"],
                    token_count=row_data["token_count"],
                    dense_rank=dense_rank,
                    sparse_rank=sparse_rank,
                    dense_similarity=dense_score,
                    sparse_rank_score=sparse_score,
                    rrf_score=rrf,
                )
            )

        # 6. Deterministic Tie-Breaking
        # ORDER BY rrf_score DESC, rank_dense ASC NULLS LAST, rank_sparse ASC NULLS LAST, chunk_id ASC
        def sort_key(c: RetrievedChunk):
            dr = c.dense_rank if c.dense_rank is not None else 999999
            sr = c.sparse_rank if c.sparse_rank is not None else 999999
            return (-c.rrf_score, dr, sr, str(c.chunk_id))

        candidates.sort(key=sort_key)

        # 7. Optional Cross-Encoder Reranking
        settings = get_settings()
        if apply_reranker and settings.RERANKER_ENABLED and self.reranker_model and candidates:
            t_rerank = time.perf_counter()
            # Take top candidate pool for reranking (e.g. up to top 20 from RRF)
            rerank_pool = candidates[:20]
            passages = [c.content for c in rerank_pool]
            rerank_results = await self.reranker_model.rerank(query, passages, top_k=top_k)
            rag_rerank_duration_seconds.observe(time.perf_counter() - t_rerank)

            reranked_chunks: List[RetrievedChunk] = []
            for rank_pos, (orig_idx, score) in enumerate(rerank_results, start=1):
                chunk = rerank_pool[orig_idx]
                chunk.rerank_score = score
                chunk.citation_marker = rank_pos
                reranked_chunks.append(chunk)

            return reranked_chunks
        else:
            # Return top_k directly from deterministic RRF
            final_chunks = candidates[:top_k]
            for rank_pos, chunk in enumerate(final_chunks, start=1):
                chunk.citation_marker = rank_pos
            return final_chunks
