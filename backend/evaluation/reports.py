"""
DevVision AI - Evaluation Report Generators.

Outputs:
1. Machine-readable JSON: `backend/evaluation/results/evaluation_report.json`
2. Human-readable Markdown: `backend/evaluation/results/latest_report.md`

Includes:
- Dataset metadata & category breakdown
- Retrieval ablation comparison (Dense, Sparse, Hybrid RRF, Hybrid RRF + Reranker)
- Relative lift metrics (RRF over Dense, Reranker over RRF)
- Citation & grounding metrics
- Adversarial attack resilience rates
- Baseline regression analysis
- Production acceptance gate verdicts
"""

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Dict, Optional

from evaluation.models import EvaluationReport


def generate_json_report(report: EvaluationReport, output_path: Path) -> None:
    """
    Serializes EvaluationReport to structured JSON format.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_dict = asdict(report)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2)


def generate_markdown_report(report: EvaluationReport, output_path: Path) -> None:
    """
    Renders human-readable markdown report with summary tables, alerts, and detailed breakdowns.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ab = report.ablation_results
    adv = report.adversarial_results
    acc = report.acceptance

    verdict_badge = "**PASS**" if acc.passed else "**FAIL**"

    lines = []
    lines.append("# DevVision AI — Phase 6 RAG Quality & Acceptance Report")
    lines.append("")
    lines.append(f"**Run ID**: `{report.run_id}`  ")
    lines.append(f"**Timestamp**: `{report.timestamp}`  ")
    lines.append(f"**Dataset**: `{report.dataset_name}` (Version: `{report.dataset_version}`, Cases: `{report.dataset_case_count}`)  ")
    lines.append(f"**Production Acceptance Verdict**: {verdict_badge}  ")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. Executive Summary & Acceptance Gates")
    lines.append("")
    lines.append("| Gate Metric | Observed | Target | Status |")
    lines.append("| :--- | :---: | :---: | :---: |")

    for g in acc.gates:
        status_icon = "PASS" if g.passed else "FAIL"
        lines.append(f"| `{g.gate_name}` | **{g.observed_value:.4f}** | {g.comparator} {g.target_threshold:.4f} | {status_icon} |")

    if acc.failed_conditions:
        lines.append("")
        lines.append("> [!CAUTION]")
        lines.append("> **Acceptance Gate Failures Detected**:")
        for fail in acc.failed_conditions:
            lines.append(f"> - {fail}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 2. Retrieval Ablation Comparison")
    lines.append("")
    lines.append("Evaluates 4 retrieval modes across the exact same evaluation queries under identical conditions:")
    lines.append("1. **Dense Only**: Semantic vector similarity (pgvector cosine distance).")
    lines.append("2. **Sparse Only**: Lexical full-text search (PostgreSQL tsvector / plainto_tsquery).")
    lines.append("3. **Hybrid RRF**: Reciprocal Rank Fusion (k=60).")
    lines.append("4. **Hybrid RRF + Reranker**: Hybrid candidate pool reranked by self-hosted BGE Cross-Encoder.")
    lines.append("")
    lines.append("| Metric | Dense Only | Sparse Only | Hybrid RRF | Hybrid RRF + Reranker |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    lines.append(f"| **Recall@1** | {ab.dense_only.retrieval.recall_at_1:.4f} | {ab.sparse_only.retrieval.recall_at_1:.4f} | {ab.hybrid_rrf.retrieval.recall_at_1:.4f} | {ab.hybrid_rerank.retrieval.recall_at_1:.4f} |")
    lines.append(f"| **Recall@3** | {ab.dense_only.retrieval.recall_at_3:.4f} | {ab.sparse_only.retrieval.recall_at_3:.4f} | {ab.hybrid_rrf.retrieval.recall_at_3:.4f} | {ab.hybrid_rerank.retrieval.recall_at_3:.4f} |")
    lines.append(f"| **Recall@5** | {ab.dense_only.retrieval.recall_at_5:.4f} | {ab.sparse_only.retrieval.recall_at_5:.4f} | {ab.hybrid_rrf.retrieval.recall_at_5:.4f} | {ab.hybrid_rerank.retrieval.recall_at_5:.4f} |")
    lines.append(f"| **Recall@10** | {ab.dense_only.retrieval.recall_at_10:.4f} | {ab.sparse_only.retrieval.recall_at_10:.4f} | {ab.hybrid_rrf.retrieval.recall_at_10:.4f} | {ab.hybrid_rerank.retrieval.recall_at_10:.4f} |")
    lines.append(f"| **Precision@5** | {ab.dense_only.retrieval.precision_at_5:.4f} | {ab.sparse_only.retrieval.precision_at_5:.4f} | {ab.hybrid_rrf.retrieval.precision_at_5:.4f} | {ab.hybrid_rerank.retrieval.precision_at_5:.4f} |")
    lines.append(f"| **MRR** | {ab.dense_only.retrieval.mrr:.4f} | {ab.sparse_only.retrieval.mrr:.4f} | {ab.hybrid_rrf.retrieval.mrr:.4f} | {ab.hybrid_rerank.retrieval.mrr:.4f} |")
    lines.append(f"| **NDCG@5** | {ab.dense_only.retrieval.ndcg_at_5:.4f} | {ab.sparse_only.retrieval.ndcg_at_5:.4f} | {ab.hybrid_rrf.retrieval.ndcg_at_5:.4f} | {ab.hybrid_rerank.retrieval.ndcg_at_5:.4f} |")
    lines.append(f"| **HitRate@5** | {ab.dense_only.retrieval.hit_rate_at_5:.4f} | {ab.sparse_only.retrieval.hit_rate_at_5:.4f} | {ab.hybrid_rrf.retrieval.hit_rate_at_5:.4f} | {ab.hybrid_rerank.retrieval.hit_rate_at_5:.4f} |")
    lines.append(f"| **P50 Latency (ms)** | {ab.dense_only.retrieval.p50_latency_ms:.2f} | {ab.sparse_only.retrieval.p50_latency_ms:.2f} | {ab.hybrid_rrf.retrieval.p50_latency_ms:.2f} | {ab.hybrid_rerank.retrieval.p50_latency_ms:.2f} |")
    lines.append(f"| **P95 Latency (ms)** | {ab.dense_only.retrieval.p95_latency_ms:.2f} | {ab.sparse_only.retrieval.p95_latency_ms:.2f} | {ab.hybrid_rrf.retrieval.p95_latency_ms:.2f} | {ab.hybrid_rerank.retrieval.p95_latency_ms:.2f} |")
    lines.append("")
    lines.append("### Relative Metric Lifts")
    lines.append(f"- **Hybrid RRF vs. Dense Only Recall@5 Lift**: `{ab.relative_lift_rrf_over_dense.get('recall_at_5_lift_pct', 0.0):+.2f}%`")
    lines.append(f"- **Hybrid RRF vs. Dense Only MRR Lift**: `{ab.relative_lift_rrf_over_dense.get('mrr_lift_pct', 0.0):+.2f}%`")
    lines.append(f"- **Reranker vs. Hybrid RRF Recall@5 Lift**: `{ab.relative_lift_rerank_over_rrf.get('recall_at_5_lift_pct', 0.0):+.2f}%`")
    lines.append(f"- **Reranker vs. Hybrid RRF MRR Lift**: `{ab.relative_lift_rerank_over_rrf.get('mrr_lift_pct', 0.0):+.2f}%`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 3. Grounding & Citation Quality Evaluation")
    lines.append("")
    lines.append("Evaluates sentence-level citation validity and provenance enforcement:")
    cit_prec = ab.hybrid_rerank.citation.citation_precision if ab.hybrid_rerank.citation else 1.0
    cit_rec = ab.hybrid_rerank.citation.citation_recall if ab.hybrid_rerank.citation else 1.0
    unsupp = ab.hybrid_rerank.citation.unsupported_claim_rate if ab.hybrid_rerank.citation else 0.0
    inv_m = ab.hybrid_rerank.citation.invalid_marker_rate if ab.hybrid_rerank.citation else 0.0
    sem_inv = ab.hybrid_rerank.citation.semantic_contradiction_rate if ab.hybrid_rerank.citation else 0.0
    lines.append(f"- **Citation Precision**: `{cit_prec:.4f}` (Fraction of attached citations supporting their sentence)")
    lines.append(f"- **Citation Recall**: `{cit_rec:.4f}` (Fraction of expected facts with verified citations)")
    lines.append(f"- **Unsupported Claim Rate**: `{unsupp:.4f}` (Sentences with unverified assertions)")
    lines.append(f"- **Invalid Marker Rate**: `{inv_m:.4f}` (Citations referencing non-existent context excerpts)")
    lines.append(f"- **Semantic Contradiction Rate**: `{sem_inv:.4f}` (Negation / polarity flips)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 4. Adversarial Attack & Security Resilience")
    lines.append("")
    lines.append("| Adversarial Category | Total Cases | Passed | Escape / Leak Rate | Status |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    inj_status = "PASS" if adv.prompt_injection_escape_rate == 0 else "FAIL"
    iso_status = "PASS" if adv.cross_tenant_leak_rate == 0 else "FAIL"
    stale_status = "PASS" if adv.stale_generation_leak_rate == 0 else "FAIL"
    lines.append(f"| **Prompt Injection Defense** | {adv.total_adversarial_cases} | {adv.passed_cases} | **{adv.prompt_injection_escape_rate:.2%}** | {inj_status} |")
    lines.append(f"| **Cross-Tenant Isolation** | - | - | **{adv.cross_tenant_leak_rate:.2%}** | {iso_status} |")
    lines.append(f"| **Stale Generation Shield** | - | - | **{adv.stale_generation_leak_rate:.2%}** | {stale_status} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 5. Baseline Comparison & Regression Check")
    lines.append("")

    base_comp = report.baseline_comparison
    if base_comp and base_comp.get("has_baseline"):
        has_reg = base_comp.get("has_regressions", False)
        status_str = "**REGRESSIONS DETECTED**" if has_reg else "**NO REGRESSIONS**"
        lines.append(f"**Baseline Version**: `{base_comp.get('baseline_version')}`  ")
        lines.append(f"**Comparison Status**: {status_str}  ")
        lines.append("")
        lines.append("| Metric | Current | Baseline | Delta (%) |")
        lines.append("| :--- | :---: | :---: | :---: |")
        for m_name, diff in base_comp.get("metrics_diff", {}).items():
            lines.append(f"| `{m_name}` | {diff['current']:.4f} | {diff['baseline']:.4f} | {diff['pct_change']:+.2f}% |")

        if has_reg:
            lines.append("")
            lines.append("> [!WARNING]")
            lines.append("> **Regressions vs Baseline**:")
            for reg in base_comp.get("regressions", []):
                lines.append(f"> - {reg}")
    else:
        lines.append("*No baseline file found for regression comparison. Run with `--write-baseline` to establish.*")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
