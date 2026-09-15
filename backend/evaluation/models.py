"""
DevVision AI - Phase 6 Evaluation Data Models and Schemas.

Defines schemas for:
- EvaluationCase and EvaluationDataset
- RetrievalMetricsResult and CitationMetricsResult
- AblationResult (Dense, Sparse, Hybrid RRF, Hybrid RRF + Reranker)
- Production Acceptance Gates & Baselines
- Comprehensive EvaluationReport
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class CaseCategory(str, Enum):
    FACTUAL_LOOKUP = "factual_lookup"
    MULTI_CHUNK_REASONING = "multi_chunk_reasoning"
    NEGATION = "negation"
    ENTITY_INVERSION = "entity_inversion"
    CONTRADICTORY_DOCS = "contradictory_docs"
    OUTDATED_GENERATION = "outdated_generation"
    PROMPT_INJECTION = "prompt_injection"
    CROSS_TENANT_ISOLATION = "cross_tenant_isolation"
    EMPTY_RETRIEVAL = "empty_retrieval"


class CaseDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class EvaluationCase:
    case_id: str
    query: str
    expected_document_ids: List[str] = field(default_factory=list)
    expected_chunk_ids: List[str] = field(default_factory=list)
    expected_facts: List[str] = field(default_factory=list)
    negative_document_ids: List[str] = field(default_factory=list)
    negative_chunk_ids: List[str] = field(default_factory=list)
    category: CaseCategory = CaseCategory.FACTUAL_LOOKUP
    difficulty: CaseDifficulty = CaseDifficulty.MEDIUM
    tags: List[str] = field(default_factory=list)
    description: str = ""
    target_workspace_id: Optional[str] = None
    adversarial_payload: Optional[str] = None


@dataclass
class EvaluationDataset:
    name: str
    version: str
    description: str
    created_at: str
    cases: List[EvaluationCase] = field(default_factory=list)


@dataclass
class RetrievalMetricsResult:
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    precision_at_1: float = 0.0
    precision_at_3: float = 0.0
    precision_at_5: float = 0.0
    precision_at_10: float = 0.0
    mrr: float = 0.0
    ndcg_at_1: float = 0.0
    ndcg_at_3: float = 0.0
    ndcg_at_5: float = 0.0
    ndcg_at_10: float = 0.0
    hit_rate_at_1: float = 0.0
    hit_rate_at_3: float = 0.0
    hit_rate_at_5: float = 0.0
    hit_rate_at_10: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    total_evaluated_queries: int = 0


@dataclass
class CitationMetricsResult:
    citation_precision: float = 1.0
    citation_recall: float = 1.0
    unsupported_claim_rate: float = 0.0
    invalid_marker_rate: float = 0.0
    missing_citation_rate: float = 0.0
    semantic_contradiction_rate: float = 0.0
    total_sentences: int = 0
    total_citations: int = 0
    valid_citations: int = 0


@dataclass
class ModeMetrics:
    mode_name: str
    retrieval: RetrievalMetricsResult
    citation: Optional[CitationMetricsResult] = None


@dataclass
class AblationResult:
    dense_only: ModeMetrics
    sparse_only: ModeMetrics
    hybrid_rrf: ModeMetrics
    hybrid_rerank: ModeMetrics
    relative_lift_rrf_over_dense: Dict[str, float] = field(default_factory=dict)
    relative_lift_rerank_over_rrf: Dict[str, float] = field(default_factory=dict)


@dataclass
class AcceptanceGateResult:
    passed: bool
    gate_name: str
    target_threshold: float
    observed_value: float
    comparator: str  # ">=", "<=", "=="
    message: str


@dataclass
class AcceptanceReport:
    overall_verdict: str  # "PASS" or "FAIL"
    passed: bool
    gates: List[AcceptanceGateResult] = field(default_factory=list)
    failed_conditions: List[str] = field(default_factory=list)


@dataclass
class AdversarialResult:
    prompt_injection_escape_rate: float = 0.0
    cross_tenant_leak_rate: float = 0.0
    stale_generation_leak_rate: float = 0.0
    distractor_confusion_rate: float = 0.0
    negation_inversion_rate: float = 0.0
    empty_retrieval_hallucination_rate: float = 0.0
    total_adversarial_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    failed_case_ids: List[str] = field(default_factory=list)


@dataclass
class EvaluationReport:
    run_id: str
    timestamp: str
    dataset_name: str
    dataset_version: str
    dataset_case_count: int
    category_distribution: Dict[str, int]
    ablation_results: AblationResult
    adversarial_results: AdversarialResult
    acceptance: AcceptanceReport
    baseline_comparison: Optional[Dict[str, Any]] = None
    failed_cases: List[Dict[str, Any]] = field(default_factory=list)
