"""
DevVision AI - Pure-Python Information Retrieval Metrics.

Evaluates ranking lists mathematically:
- Recall@K
- Precision@K
- MRR (Mean Reciprocal Rank)
- NDCG@K (Normalized Discounted Cumulative Gain)
- HitRate@K

Supports document-level and chunk-level relevance assessments.
Uses exact mathematical formulations with zero third-party/external dependencies.
"""

import math
from typing import Any, Collection, Dict, List, Optional, Sequence, Set, Union
from evaluation.models import RetrievalMetricsResult


def recall_at_k(
    retrieved: Sequence[str],
    relevant: Collection[str],
    k: int,
) -> float:
    """
    Recall@K = |retrieved[:k] ∩ relevant| / |relevant|
    Returns 1.0 if relevant set is empty (nothing relevant to recall).
    """
    if not relevant:
        return 1.0
    if k <= 0:
        return 0.0

    retrieved_k = set(retrieved[:k])
    relevant_set = set(relevant)
    intersection = retrieved_k.intersection(relevant_set)
    return len(intersection) / len(relevant_set)


def precision_at_k(
    retrieved: Sequence[str],
    relevant: Collection[str],
    k: int,
) -> float:
    """
    Precision@K = |retrieved[:k] ∩ relevant| / k
    Returns 0.0 if k <= 0.
    """
    if k <= 0:
        return 0.0

    retrieved_k = set(retrieved[:k])
    relevant_set = set(relevant)
    intersection = retrieved_k.intersection(relevant_set)
    return len(intersection) / float(k)


def reciprocal_rank(
    retrieved: Sequence[str],
    relevant: Collection[str],
) -> float:
    """
    Reciprocal Rank = 1 / rank of first relevant item in retrieved list (1-indexed).
    Returns 1.0 if relevant set is empty (unanswerable/empty query with no false positive targets).
    Returns 0.0 if no relevant item is found in non-empty relevant set.
    """
    if not relevant:
        return 1.0
    relevant_set = set(relevant)
    for idx, item in enumerate(retrieved, start=1):
        if item in relevant_set:
            return 1.0 / idx
    return 0.0


def dcg_at_k(
    retrieved: Sequence[str],
    relevant: Collection[str],
    k: int,
) -> float:
    """
    Discounted Cumulative Gain at K using standard binary relevance:
    DCG@K = sum_{i=1..min(k, len(retrieved))} (2^rel_i - 1) / log2(i + 1)
    where rel_i = 1 if retrieved[i-1] in relevant else 0.
    """
    if k <= 0:
        return 0.0

    relevant_set = set(relevant)
    dcg = 0.0
    limit = min(k, len(retrieved))
    for i in range(1, limit + 1):
        item = retrieved[i - 1]
        rel = 1 if item in relevant_set else 0
        if rel > 0:
            dcg += (2.0**rel - 1.0) / math.log2(i + 1)
    return dcg


def ndcg_at_k(
    retrieved: Sequence[str],
    relevant: Collection[str],
    k: int,
) -> float:
    """
    Normalized Discounted Cumulative Gain at K:
    NDCG@K = DCG@K / IDCG@K
    If IDCG@K is 0 (i.e. no relevant documents), returns 1.0 if retrieved has no relevant else 0.0.
    """
    if k <= 0:
        return 0.0

    relevant_set = set(relevant)
    if not relevant_set:
        return 1.0

    actual_dcg = dcg_at_k(retrieved, relevant_set, k)

    # Ideal DCG: top min(k, len(relevant)) slots are all relevant
    num_ideal = min(k, len(relevant_set))
    idcg = 0.0
    for i in range(1, num_ideal + 1):
        idcg += (2.0**1 - 1.0) / math.log2(i + 1)

    if idcg == 0.0:
        return 1.0

    return actual_dcg / idcg


def hit_rate_at_k(
    retrieved: Sequence[str],
    relevant: Collection[str],
    k: int,
) -> float:
    """
    HitRate@K = 1.0 if |retrieved[:k] ∩ relevant| > 0 else 0.0
    If no relevant items exist, returns 1.0.
    """
    if not relevant:
        return 1.0
    if k <= 0:
        return 0.0

    retrieved_k = set(retrieved[:k])
    relevant_set = set(relevant)
    return 1.0 if len(retrieved_k.intersection(relevant_set)) > 0 else 0.0


def compute_retrieval_metrics(
    eval_queries: List[Dict[str, Any]],
    k_values: Sequence[int] = (1, 3, 5, 10),
    use_chunk_ids: bool = False,
) -> RetrievalMetricsResult:
    """
    Computes aggregated macro-averaged retrieval metrics across all queries.
    eval_queries item format:
    {
        "retrieved_doc_ids": List[str],
        "expected_doc_ids": List[str],
        "retrieved_chunk_ids": Optional[List[str]],
        "expected_chunk_ids": Optional[List[str]],
        "latency_ms": Optional[float]
    }
    """
    if not eval_queries:
        return RetrievalMetricsResult()

    n = len(eval_queries)
    recalls: Dict[int, float] = {k: 0.0 for k in k_values}
    precisions: Dict[int, float] = {k: 0.0 for k in k_values}
    ndcgs: Dict[int, float] = {k: 0.0 for k in k_values}
    hit_rates: Dict[int, float] = {k: 0.0 for k in k_values}
    mrr_sum = 0.0
    latencies: List[float] = []

    for q in eval_queries:
        if use_chunk_ids and q.get("expected_chunk_ids"):
            retrieved = q.get("retrieved_chunk_ids", [])
            relevant = q.get("expected_chunk_ids", [])
        else:
            retrieved = q.get("retrieved_doc_ids", [])
            relevant = q.get("expected_doc_ids", [])

        if "latency_ms" in q and q["latency_ms"] is not None:
            latencies.append(float(q["latency_ms"]))

        # MRR
        mrr_sum += reciprocal_rank(retrieved, relevant)

        # K-level metrics
        for k in k_values:
            recalls[k] += recall_at_k(retrieved, relevant, k)
            precisions[k] += precision_at_k(retrieved, relevant, k)
            ndcgs[k] += ndcg_at_k(retrieved, relevant, k)
            hit_rates[k] += hit_rate_at_k(retrieved, relevant, k)

    # Latencies percentiles
    p50 = 0.0
    p95 = 0.0
    p99 = 0.0
    if latencies:
        latencies.sort()
        idx50 = int(round(0.50 * (len(latencies) - 1)))
        idx95 = int(round(0.95 * (len(latencies) - 1)))
        idx99 = int(round(0.99 * (len(latencies) - 1)))
        p50 = latencies[idx50]
        p95 = latencies[idx95]
        p99 = latencies[idx99]

    return RetrievalMetricsResult(
        recall_at_1=round(recalls.get(1, 0.0) / n, 4),
        recall_at_3=round(recalls.get(3, 0.0) / n, 4),
        recall_at_5=round(recalls.get(5, 0.0) / n, 4),
        recall_at_10=round(recalls.get(10, 0.0) / n, 4),
        precision_at_1=round(precisions.get(1, 0.0) / n, 4),
        precision_at_3=round(precisions.get(3, 0.0) / n, 4),
        precision_at_5=round(precisions.get(5, 0.0) / n, 4),
        precision_at_10=round(precisions.get(10, 0.0) / n, 4),
        mrr=round(mrr_sum / n, 4),
        ndcg_at_1=round(ndcgs.get(1, 0.0) / n, 4),
        ndcg_at_3=round(ndcgs.get(3, 0.0) / n, 4),
        ndcg_at_5=round(ndcgs.get(5, 0.0) / n, 4),
        ndcg_at_10=round(ndcgs.get(10, 0.0) / n, 4),
        hit_rate_at_1=round(hit_rates.get(1, 0.0) / n, 4),
        hit_rate_at_3=round(hit_rates.get(3, 0.0) / n, 4),
        hit_rate_at_5=round(hit_rates.get(5, 0.0) / n, 4),
        hit_rate_at_10=round(hit_rates.get(10, 0.0) / n, 4),
        p50_latency_ms=round(p50, 2),
        p95_latency_ms=round(p95, 2),
        p99_latency_ms=round(p99, 2),
        total_evaluated_queries=n,
    )
