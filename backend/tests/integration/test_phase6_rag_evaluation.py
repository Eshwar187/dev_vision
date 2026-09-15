"""
DevVision AI - Phase 6 RAG Evaluation Integration Test Suite.

Verifies:
1. Benchmark dataset loading and schema validation.
2. 4-way retrieval ablation execution (Dense, Sparse, Hybrid RRF, Hybrid RRF + Reranker).
3. Grounding and citation validation assessment.
4. Report serialization (JSON & Markdown outputs).
5. Production acceptance gates enforcement.
6. Baseline regression detection (detects degradation vs baseline).
7. Baseline immutability invariant: failing run NEVER replaces stored baseline without --write-baseline.
"""

import json
from pathlib import Path
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.modules.rag.mock import MockEmbeddingModel, MockRerankerModel, MockLanguageModel
from app.modules.rag.retrieval import HybridRetrievalService
from app.modules.rag.service import RagService
from evaluation.dataset_loader import load_dataset
from evaluation.runner import RagEvaluationOrchestrator
from evaluation.acceptance import AcceptanceGateEvaluator
from evaluation.models import RetrievalMetricsResult, CitationMetricsResult, AdversarialResult

# In-memory test SQLite database for fast deterministic evaluation tests
eval_test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

EvalTestingSessionLocal = async_sessionmaker(
    bind=eval_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@pytest.fixture(autouse=True)
async def init_eval_db():
    async with eval_test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with eval_test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def eval_orchestrator():
    embedding = MockEmbeddingModel()
    reranker = MockRerankerModel()
    llm = MockLanguageModel()
    retrieval = HybridRetrievalService(embedding_model=embedding, reranker_model=reranker)
    rag = RagService(embedding_model=embedding, reranker_model=reranker, language_model=llm)
    return RagEvaluationOrchestrator(
        retrieval_service=retrieval,
        rag_service=rag,
        session_factory=EvalTestingSessionLocal,
    )


@pytest.mark.asyncio
async def test_dataset_loader_integrity():
    dataset_file = Path(__file__).parent.parent.parent / "evaluation" / "datasets" / "curated_benchmark.json"
    dataset = load_dataset(dataset_file)
    assert dataset.name == "DevVision Curated Technical Documentation Benchmark"
    assert len(dataset.cases) >= 35, "Dataset must contain at least 35 realistic cases"

    # Verify category distribution
    categories = {c.category.value for c in dataset.cases}
    assert "factual_lookup" in categories
    assert "multi_chunk_reasoning" in categories
    assert "negation" in categories
    assert "entity_inversion" in categories
    assert "prompt_injection" in categories
    assert "cross_tenant_isolation" in categories
    assert "empty_retrieval" in categories


@pytest.mark.asyncio
async def test_full_rag_evaluation_run(tmp_path, eval_orchestrator):
    dataset_file = Path(__file__).parent.parent.parent / "evaluation" / "datasets" / "curated_benchmark.json"
    baseline_file = Path(__file__).parent.parent.parent / "evaluation" / "baselines" / "baseline_phase6.json"
    out_dir = tmp_path / "results"

    report = await eval_orchestrator.run_evaluation(
        dataset_path=dataset_file,
        baseline_path=baseline_file,
        output_dir=out_dir,
        write_baseline=False,
    )

    # 1. Verify report structure
    assert report.dataset_case_count >= 35
    assert len(report.category_distribution) >= 6

    # 2. Verify all 4 ablation modes executed
    ab = report.ablation_results
    assert ab.dense_only.retrieval.total_evaluated_queries == report.dataset_case_count
    assert ab.sparse_only.retrieval.total_evaluated_queries == report.dataset_case_count
    assert ab.hybrid_rrf.retrieval.total_evaluated_queries == report.dataset_case_count
    assert ab.hybrid_rerank.retrieval.total_evaluated_queries == report.dataset_case_count

    # 3. Verify metrics are non-trivial
    assert ab.hybrid_rerank.retrieval.recall_at_5 > 0.50
    assert ab.hybrid_rerank.retrieval.mrr > 0.50
    assert ab.hybrid_rerank.retrieval.ndcg_at_5 > 0.50

    # 4. Verify citation evaluation metrics
    cit = ab.hybrid_rerank.citation
    assert cit is not None
    assert cit.citation_precision >= 0.85
    assert cit.unsupported_claim_rate <= 0.15

    # 5. Verify reports written to disk
    json_path = out_dir / "evaluation_report.json"
    md_path = out_dir / "latest_report.md"
    assert json_path.is_file()
    assert md_path.is_file()

    with open(json_path, "r", encoding="utf-8") as f:
        saved_json = json.load(f)
    assert saved_json["run_id"] == report.run_id


@pytest.mark.asyncio
async def test_acceptance_gate_logic():
    evaluator = AcceptanceGateEvaluator()

    # Case A: Metrics meeting all criteria
    retrieval_pass = RetrievalMetricsResult(
        recall_at_5=0.88,
        mrr=0.76,
        ndcg_at_5=0.82,
    )
    citation_pass = CitationMetricsResult(
        citation_precision=0.96,
        unsupported_claim_rate=0.04,
    )
    adv_pass = AdversarialResult(
        cross_tenant_leak_rate=0.0,
        prompt_injection_escape_rate=0.0,
        stale_generation_leak_rate=0.0,
    )
    res_pass = evaluator.evaluate_acceptance(retrieval_pass, citation_pass, adv_pass)
    assert res_pass.passed is True
    assert res_pass.overall_verdict == "PASS"
    assert len(res_pass.failed_conditions) == 0

    # Case B: Recall regression failing gate
    retrieval_fail = RetrievalMetricsResult(
        recall_at_5=0.70,  # Below 0.80
        mrr=0.76,
        ndcg_at_5=0.82,
    )
    res_fail = evaluator.evaluate_acceptance(retrieval_fail, citation_pass, adv_pass)
    assert res_fail.passed is False
    assert res_fail.overall_verdict == "FAIL"
    assert any("retrieval_recall_at_5" in cond for cond in res_fail.failed_conditions)


@pytest.mark.asyncio
async def test_baseline_regression_detection(tmp_path):
    evaluator = AcceptanceGateEvaluator()
    fake_baseline = tmp_path / "baseline.json"
    with open(fake_baseline, "w", encoding="utf-8") as f:
        json.dump({
            "version": "1.0.0",
            "recall_at_5": 0.90,
            "mrr": 0.80,
            "ndcg_at_5": 0.85,
            "citation_precision": 0.98,
            "unsupported_claim_rate": 0.02,
            "p95_latency_ms": 200.0,
        }, f)

    # Current metrics with significant regression in recall_at_5 (0.80 is > 5% drop from 0.90)
    current_retrieval = RetrievalMetricsResult(
        recall_at_5=0.80,
        mrr=0.80,
        ndcg_at_5=0.85,
        p95_latency_ms=210.0,
    )
    current_citation = CitationMetricsResult(
        citation_precision=0.98,
        unsupported_claim_rate=0.02,
    )

    comp = evaluator.compare_with_baseline(current_retrieval, current_citation, fake_baseline)
    assert comp["has_baseline"] is True
    assert comp["has_regressions"] is True
    assert any("retrieval_recall_at_5" in reg for reg in comp["regressions"])


@pytest.mark.asyncio
async def test_baseline_immutability_on_failure(tmp_path, eval_orchestrator):
    """
    CRITICAL INVARIANT: A failed evaluation run must NEVER automatically
    replace or modify the stored baseline file.
    """
    dataset_file = Path(__file__).parent.parent.parent / "evaluation" / "datasets" / "curated_benchmark.json"
    baseline_file = tmp_path / "baseline_immutable.json"

    initial_baseline_content = {
        "version": "1.0.0",
        "recall_at_5": 0.95,
        "mrr": 0.85,
        "notes": "Untouchable initial baseline",
    }
    with open(baseline_file, "w", encoding="utf-8") as f:
        json.dump(initial_baseline_content, f, indent=2)

    # Run without --write-baseline
    await eval_orchestrator.run_evaluation(
        dataset_path=dataset_file,
        baseline_path=baseline_file,
        output_dir=tmp_path / "results",
        write_baseline=False,
    )

    # Content of baseline file must be strictly untouched
    with open(baseline_file, "r", encoding="utf-8") as f:
        after_run_content = json.load(f)

    assert after_run_content["notes"] == "Untouchable initial baseline"
    assert after_run_content["recall_at_5"] == 0.95
