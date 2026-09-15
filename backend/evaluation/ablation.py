"""
DevVision AI - Retrieval Ablation Engine.

Evaluates 4 retrieval modes across evaluation queries:
1. Dense Only: Semantic cosine similarity (pgvector).
2. Sparse Only: Lexical full-text search (tsvector plainto_tsquery).
3. Hybrid RRF: Reciprocal Rank Fusion (k=60).
4. Hybrid RRF + Reranker: Hybrid candidate set reranked by BGE Cross-Encoder.

Computes exact macro-averaged ranking metrics and relative lifts without altering production defaults.
"""

import time
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.modules.rag.retrieval import HybridRetrievalService, RetrievedChunk
from evaluation.models import AblationResult, ModeMetrics, RetrievalMetricsResult
from evaluation.metrics import compute_retrieval_metrics

logger = structlog.get_logger(__name__)


class RetrievalAblationRunner:
    """
    Orchestrates execution and metric comparison across all 4 retrieval configurations.
    """

    def __init__(self, retrieval_service: HybridRetrievalService):
        self.retrieval_service = retrieval_service

    async def evaluate_single_query(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        query: str,
        expected_doc_ids: List[str],
        expected_chunk_ids: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Executes a single query across all 4 configurations and returns retrieved ids and timings.
        """
        results = {}

        # 1. Dense Only (apply_reranker=False, retrieval_mode="dense_only")
        t0 = time.perf_counter()
        dense_chunks = await self.retrieval_service.retrieve(
            db=db,
            workspace_id=workspace_id,
            query=query,
            top_k=top_k,
            apply_reranker=False,
            retrieval_mode="dense_only",
        )
        lat_dense = (time.perf_counter() - t0) * 1000.0
        results["dense_only"] = {
            "retrieved_doc_ids": [str(c.document_id) for c in dense_chunks],
            "retrieved_chunk_ids": [str(c.chunk_id) for c in dense_chunks],
            "expected_doc_ids": expected_doc_ids,
            "expected_chunk_ids": expected_chunk_ids or [],
            "latency_ms": lat_dense,
        }

        # 2. Sparse Only (apply_reranker=False, retrieval_mode="sparse_only")
        t0 = time.perf_counter()
        sparse_chunks = await self.retrieval_service.retrieve(
            db=db,
            workspace_id=workspace_id,
            query=query,
            top_k=top_k,
            apply_reranker=False,
            retrieval_mode="sparse_only",
        )
        lat_sparse = (time.perf_counter() - t0) * 1000.0
        results["sparse_only"] = {
            "retrieved_doc_ids": [str(c.document_id) for c in sparse_chunks],
            "retrieved_chunk_ids": [str(c.chunk_id) for c in sparse_chunks],
            "expected_doc_ids": expected_doc_ids,
            "expected_chunk_ids": expected_chunk_ids or [],
            "latency_ms": lat_sparse,
        }

        # 3. Hybrid RRF (apply_reranker=False, retrieval_mode="hybrid_rrf")
        t0 = time.perf_counter()
        rrf_chunks = await self.retrieval_service.retrieve(
            db=db,
            workspace_id=workspace_id,
            query=query,
            top_k=top_k,
            apply_reranker=False,
            retrieval_mode="hybrid_rrf",
        )
        lat_rrf = (time.perf_counter() - t0) * 1000.0
        results["hybrid_rrf"] = {
            "retrieved_doc_ids": [str(c.document_id) for c in rrf_chunks],
            "retrieved_chunk_ids": [str(c.chunk_id) for c in rrf_chunks],
            "expected_doc_ids": expected_doc_ids,
            "expected_chunk_ids": expected_chunk_ids or [],
            "latency_ms": lat_rrf,
        }

        # 4. Hybrid RRF + Reranker (apply_reranker=True, retrieval_mode="hybrid_rrf")
        t0 = time.perf_counter()
        rerank_chunks = await self.retrieval_service.retrieve(
            db=db,
            workspace_id=workspace_id,
            query=query,
            top_k=top_k,
            apply_reranker=True,
            retrieval_mode="hybrid_rrf",
        )
        lat_rerank = (time.perf_counter() - t0) * 1000.0
        results["hybrid_rerank"] = {
            "retrieved_doc_ids": [str(c.document_id) for c in rerank_chunks],
            "retrieved_chunk_ids": [str(c.chunk_id) for c in rerank_chunks],
            "expected_doc_ids": expected_doc_ids,
            "expected_chunk_ids": expected_chunk_ids or [],
            "latency_ms": lat_rerank,
        }

        return results

    def compute_ablation_results(
        self,
        mode_queries: Dict[str, List[Dict[str, Any]]],
        use_chunk_ids: bool = False,
    ) -> AblationResult:
        """
        Computes aggregated RetrievalMetricsResult for each mode and derives relative lifts.
        """
        dense_metrics = compute_retrieval_metrics(
            mode_queries.get("dense_only", []), use_chunk_ids=use_chunk_ids
        )
        sparse_metrics = compute_retrieval_metrics(
            mode_queries.get("sparse_only", []), use_chunk_ids=use_chunk_ids
        )
        rrf_metrics = compute_retrieval_metrics(
            mode_queries.get("hybrid_rrf", []), use_chunk_ids=use_chunk_ids
        )
        rerank_metrics = compute_retrieval_metrics(
            mode_queries.get("hybrid_rerank", []), use_chunk_ids=use_chunk_ids
        )

        def _calc_lift(curr: float, base: float) -> float:
            if base == 0.0:
                return round((curr - base) * 100.0, 2)
            return round(((curr - base) / base) * 100.0, 2)

        lift_rrf = {
            "recall_at_5_lift_pct": _calc_lift(rrf_metrics.recall_at_5, dense_metrics.recall_at_5),
            "mrr_lift_pct": _calc_lift(rrf_metrics.mrr, dense_metrics.mrr),
            "ndcg_at_5_lift_pct": _calc_lift(rrf_metrics.ndcg_at_5, dense_metrics.ndcg_at_5),
        }

        lift_rerank = {
            "recall_at_5_lift_pct": _calc_lift(rerank_metrics.recall_at_5, rrf_metrics.recall_at_5),
            "mrr_lift_pct": _calc_lift(rerank_metrics.mrr, rrf_metrics.mrr),
            "ndcg_at_5_lift_pct": _calc_lift(rerank_metrics.ndcg_at_5, rrf_metrics.ndcg_at_5),
        }

        return AblationResult(
            dense_only=ModeMetrics(mode_name="dense_only", retrieval=dense_metrics),
            sparse_only=ModeMetrics(mode_name="sparse_only", retrieval=sparse_metrics),
            hybrid_rrf=ModeMetrics(mode_name="hybrid_rrf", retrieval=rrf_metrics),
            hybrid_rerank=ModeMetrics(mode_name="hybrid_rerank", retrieval=rerank_metrics),
            relative_lift_rrf_over_dense=lift_rrf,
            relative_lift_rerank_over_rrf=lift_rerank,
        )
