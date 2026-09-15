"""
Unit tests for Pure-Python Information Retrieval Metrics (Recall@K, Precision@K, MRR, NDCG@K, HitRate@K).
Validates mathematical calculations against known manual baselines.
"""

import math
import pytest
from evaluation.metrics import (
    recall_at_k,
    precision_at_k,
    reciprocal_rank,
    dcg_at_k,
    ndcg_at_k,
    hit_rate_at_k,
    compute_retrieval_metrics,
)


def test_recall_at_k_exact_math():
    retrieved = ["doc1", "doc2", "doc3", "doc4", "doc5"]
    relevant = {"doc2", "doc5", "doc7"}  # 3 relevant in total

    # At K=1: retrieved=["doc1"] -> 0 relevant
    assert recall_at_k(retrieved, relevant, k=1) == 0.0

    # At K=2: retrieved=["doc1", "doc2"] -> 1 relevant ("doc2") / 3 total = 1/3
    assert recall_at_k(retrieved, relevant, k=2) == pytest.approx(1.0 / 3.0)

    # At K=5: retrieved=["doc1", "doc2", "doc3", "doc4", "doc5"] -> 2 relevant ("doc2", "doc5") / 3 = 2/3
    assert recall_at_k(retrieved, relevant, k=5) == pytest.approx(2.0 / 3.0)

    # Edge cases
    assert recall_at_k(retrieved, set(), k=5) == 1.0  # Nothing relevant
    assert recall_at_k(retrieved, relevant, k=0) == 0.0  # k <= 0


def test_precision_at_k_exact_math():
    retrieved = ["doc1", "doc2", "doc3", "doc4", "doc5"]
    relevant = {"doc2", "doc5", "doc7"}

    # At K=1: 0/1 = 0.0
    assert precision_at_k(retrieved, relevant, k=1) == 0.0

    # At K=2: 1/2 = 0.5
    assert precision_at_k(retrieved, relevant, k=2) == 0.5

    # At K=4: 1/4 = 0.25
    assert precision_at_k(retrieved, relevant, k=4) == 0.25

    # At K=5: 2/5 = 0.4
    assert precision_at_k(retrieved, relevant, k=5) == 0.4


def test_reciprocal_rank_exact_math():
    relevant = {"doc3", "doc8"}

    # First relevant is at rank 3 -> RR = 1/3
    retrieved1 = ["doc1", "doc2", "doc3", "doc4"]
    assert reciprocal_rank(retrieved1, relevant) == pytest.approx(1.0 / 3.0)

    # First relevant is at rank 1 -> RR = 1.0
    retrieved2 = ["doc3", "doc1", "doc8"]
    assert reciprocal_rank(retrieved2, relevant) == 1.0

    # No relevant item -> RR = 0.0
    retrieved3 = ["doc1", "doc2", "doc4"]
    assert reciprocal_rank(retrieved3, relevant) == 0.0


def test_ndcg_at_k_exact_math():
    relevant = {"doc1", "doc3"}

    # Perfect ranking: ["doc1", "doc3", "doc2"]
    # DCG@2 = (2^1 - 1)/log2(2) + (2^1 - 1)/log2(3) = 1/1 + 1/1.5849625 = 1 + 0.63092975 = 1.63092975
    # IDCG@2 = 1.63092975 -> NDCG = 1.0
    perfect = ["doc1", "doc3", "doc2"]
    assert ndcg_at_k(perfect, relevant, k=2) == pytest.approx(1.0)
    assert ndcg_at_k(perfect, relevant, k=3) == pytest.approx(1.0)

    # Inverted ranking: ["doc2", "doc1", "doc3"]
    # Rank 1: doc2 (rel=0)
    # Rank 2: doc1 (rel=1) -> 1 / log2(3) = 0.63092975
    # Rank 3: doc3 (rel=1) -> 1 / log2(4) = 0.5
    # At K=2: DCG@2 = 0.63092975, IDCG@2 = 1.63092975 -> NDCG@2 ~ 0.3868
    inverted = ["doc2", "doc1", "doc3"]
    expected_ndcg_2 = (1.0 / math.log2(3)) / (1.0 + (1.0 / math.log2(3)))
    assert ndcg_at_k(inverted, relevant, k=2) == pytest.approx(expected_ndcg_2, rel=1e-4)

    # Worst ranking: ["doc2", "doc4", "doc5"]
    assert ndcg_at_k(["doc2", "doc4", "doc5"], relevant, k=3) == 0.0


def test_hit_rate_at_k_exact_math():
    retrieved = ["doc1", "doc2", "doc3"]
    relevant = {"doc2"}

    assert hit_rate_at_k(retrieved, relevant, k=1) == 0.0
    assert hit_rate_at_k(retrieved, relevant, k=2) == 1.0
    assert hit_rate_at_k(retrieved, relevant, k=3) == 1.0
    assert hit_rate_at_k(retrieved, {"doc9"}, k=3) == 0.0


def test_compute_retrieval_metrics_aggregate():
    queries = [
        {
            "retrieved_doc_ids": ["doc1", "doc2", "doc3"],
            "expected_doc_ids": ["doc1"],
            "latency_ms": 10.0,
        },
        {
            "retrieved_doc_ids": ["doc4", "doc5", "doc6"],
            "expected_doc_ids": ["doc5"],
            "latency_ms": 20.0,
        },
    ]
    # Query 1: relevant="doc1" at rank 1. Recall@1=1.0, MRR=1.0
    # Query 2: relevant="doc5" at rank 2. Recall@1=0.0, Recall@3=1.0, MRR=0.5
    # Macro avg Recall@1 = (1.0 + 0.0)/2 = 0.5
    # Macro avg Recall@3 = (1.0 + 1.0)/2 = 1.0
    # Macro avg MRR = (1.0 + 0.5)/2 = 0.75
    metrics = compute_retrieval_metrics(queries, k_values=(1, 3, 5, 10))

    assert metrics.recall_at_1 == 0.5
    assert metrics.recall_at_3 == 1.0
    assert metrics.mrr == 0.75
    assert metrics.hit_rate_at_1 == 0.5
    assert metrics.hit_rate_at_3 == 1.0
    assert metrics.total_evaluated_queries == 2
    assert metrics.p50_latency_ms == pytest.approx(15.0, abs=5.1)
