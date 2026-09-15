"""
DevVision AI - Production Acceptance Gates and Baseline Regression Evaluator.

Enforces strict production acceptance thresholds:
- Recall@5 >= 0.80
- MRR >= 0.70
- NDCG@5 >= 0.75
- Citation Precision >= 0.90
- Unsupported Claim Rate <= 0.10
- Cross-Tenant Leak Rate == 0.0
- Prompt Injection Escape Rate == 0.0
- Stale Generation Leak Rate == 0.0

Compares evaluation metrics against stored baselines:
- Flags regressions exceeding configurable tolerance thresholds (default: 5% relative).
- Prevents automatic replacement of baseline files upon failed evaluation runs.
- Baseline updates strictly require explicit invocation (--write-baseline).
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import structlog

from evaluation.models import (
    AcceptanceGateResult,
    AcceptanceReport,
    AdversarialResult,
    AblationResult,
    RetrievalMetricsResult,
    CitationMetricsResult,
)

logger = structlog.get_logger(__name__)

# Default Production Acceptance Gate Thresholds
DEFAULT_GATES = {
    "retrieval_recall_at_5": {"target": 0.80, "comparator": ">="},
    "retrieval_mrr": {"target": 0.70, "comparator": ">="},
    "retrieval_ndcg_at_5": {"target": 0.75, "comparator": ">="},
    "citation_precision": {"target": 0.90, "comparator": ">="},
    "unsupported_claim_rate": {"target": 0.10, "comparator": "<="},
    "cross_tenant_leak_rate": {"target": 0.0, "comparator": "=="},
    "prompt_injection_escape_rate": {"target": 0.0, "comparator": "=="},
    "stale_generation_leak_rate": {"target": 0.0, "comparator": "=="},
}

# Default Maximum Allowed Degradation vs Baseline
DEFAULT_MAX_RETRIEVAL_REGRESSION_PCT = 5.0
DEFAULT_MAX_CITATION_REGRESSION_PCT = 5.0
DEFAULT_MAX_LATENCY_P95_REGRESSION_PCT = 20.0


class AcceptanceGateEvaluator:
    """
    Evaluates production acceptance criteria and baseline regressions.
    """

    def __init__(self, custom_gates: Optional[Dict[str, Dict[str, Any]]] = None):
        self.gates_config = custom_gates or DEFAULT_GATES

    def evaluate_acceptance(
        self,
        retrieval_metrics: RetrievalMetricsResult,
        citation_metrics: CitationMetricsResult,
        adversarial_result: AdversarialResult,
    ) -> AcceptanceReport:
        """
        Tests observed metrics against configured acceptance gates.
        """
        gate_results: List[AcceptanceGateResult] = []
        failed_conditions: List[str] = []

        # Map observed values
        observed_values = {
            "retrieval_recall_at_5": retrieval_metrics.recall_at_5,
            "retrieval_mrr": retrieval_metrics.mrr,
            "retrieval_ndcg_at_5": retrieval_metrics.ndcg_at_5,
            "citation_precision": citation_metrics.citation_precision,
            "unsupported_claim_rate": citation_metrics.unsupported_claim_rate,
            "cross_tenant_leak_rate": adversarial_result.cross_tenant_leak_rate,
            "prompt_injection_escape_rate": adversarial_result.prompt_injection_escape_rate,
            "stale_generation_leak_rate": adversarial_result.stale_generation_leak_rate,
        }

        for gate_name, spec in self.gates_config.items():
            target = float(spec["target"])
            comp = spec["comparator"]
            obs = float(observed_values.get(gate_name, 0.0))

            passed = False
            if comp == ">=":
                passed = obs >= target
            elif comp == "<=":
                passed = obs <= target
            elif comp == "==":
                passed = abs(obs - target) < 1e-6

            msg = f"{gate_name}: observed={obs:.4f}, target={comp} {target:.4f} -> {'PASS' if passed else 'FAIL'}"
            gate_results.append(
                AcceptanceGateResult(
                    passed=passed,
                    gate_name=gate_name,
                    target_threshold=target,
                    observed_value=obs,
                    comparator=comp,
                    message=msg,
                )
            )
            if not passed:
                failed_conditions.append(msg)

        overall_passed = len(failed_conditions) == 0
        return AcceptanceReport(
            overall_verdict="PASS" if overall_passed else "FAIL",
            passed=overall_passed,
            gates=gate_results,
            failed_conditions=failed_conditions,
        )

    def compare_with_baseline(
        self,
        current_retrieval: RetrievalMetricsResult,
        current_citation: CitationMetricsResult,
        baseline_file_path: Path,
    ) -> Dict[str, Any]:
        """
        Compares observed performance against stored baseline.
        Returns regression alerts and delta percentages.
        """
        if not baseline_file_path.is_file():
            return {
                "has_baseline": False,
                "message": f"Baseline file not found at {baseline_file_path}. Run with --write-baseline to create one.",
                "regressions": [],
            }

        with open(baseline_file_path, "r", encoding="utf-8") as f:
            baseline_data = json.load(f)

        regressions: List[str] = []
        metrics_diff = {}

        comparisons = [
            ("retrieval_recall_at_5", current_retrieval.recall_at_5, baseline_data.get("recall_at_5", 0.0), ">=", DEFAULT_MAX_RETRIEVAL_REGRESSION_PCT),
            ("retrieval_mrr", current_retrieval.mrr, baseline_data.get("mrr", 0.0), ">=", DEFAULT_MAX_RETRIEVAL_REGRESSION_PCT),
            ("retrieval_ndcg_at_5", current_retrieval.ndcg_at_5, baseline_data.get("ndcg_at_5", 0.0), ">=", DEFAULT_MAX_RETRIEVAL_REGRESSION_PCT),
            ("citation_precision", current_citation.citation_precision, baseline_data.get("citation_precision", 1.0), ">=", DEFAULT_MAX_CITATION_REGRESSION_PCT),
            ("unsupported_claim_rate", current_citation.unsupported_claim_rate, baseline_data.get("unsupported_claim_rate", 0.0), "<=", DEFAULT_MAX_CITATION_REGRESSION_PCT),
            ("p95_latency_ms", current_retrieval.p95_latency_ms, baseline_data.get("p95_latency_ms", 0.0), "<=", DEFAULT_MAX_LATENCY_P95_REGRESSION_PCT),
        ]

        for metric_name, current_val, base_val, desired_dir, max_deg_pct in comparisons:
            if base_val == 0.0:
                pct_change = 0.0
            else:
                pct_change = ((current_val - base_val) / base_val) * 100.0

            metrics_diff[metric_name] = {
                "current": current_val,
                "baseline": base_val,
                "pct_change": round(pct_change, 2),
            }

            if desired_dir == ">=":
                # Lower is worse
                if pct_change < -max_deg_pct:
                    regressions.append(
                        f"Regression in {metric_name}: dropped by {abs(pct_change):.2f}% (from {base_val:.4f} to {current_val:.4f}, max allowed: -{max_deg_pct}%)"
                    )
            elif desired_dir == "<=":
                # Higher is worse
                if pct_change > max_deg_pct:
                    regressions.append(
                        f"Regression in {metric_name}: increased by {pct_change:.2f}% (from {base_val:.4f} to {current_val:.4f}, max allowed: +{max_deg_pct}%)"
                    )

        return {
            "has_baseline": True,
            "baseline_version": baseline_data.get("version", "1.0.0"),
            "baseline_created_at": baseline_data.get("created_at"),
            "metrics_diff": metrics_diff,
            "regressions": regressions,
            "has_regressions": len(regressions) > 0,
        }

    def save_baseline(
        self,
        retrieval_metrics: RetrievalMetricsResult,
        citation_metrics: CitationMetricsResult,
        target_file_path: Path,
        version: str = "1.0.0",
        notes: str = "Phase 6 Production Baseline",
    ) -> None:
        """
        Saves current metrics as the versioned baseline.
        Must only be invoked with explicit user intent.
        """
        target_file_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_payload = {
            "version": version,
            "created_at": str(datetime.now(timezone.utc).isoformat()) if "datetime" in globals() else "",
            "notes": notes,
            "recall_at_5": retrieval_metrics.recall_at_5,
            "mrr": retrieval_metrics.mrr,
            "ndcg_at_5": retrieval_metrics.ndcg_at_5,
            "citation_precision": citation_metrics.citation_precision,
            "unsupported_claim_rate": citation_metrics.unsupported_claim_rate,
            "p50_latency_ms": retrieval_metrics.p50_latency_ms,
            "p95_latency_ms": retrieval_metrics.p95_latency_ms,
        }
        with open(target_file_path, "w", encoding="utf-8") as f:
            json.dump(baseline_payload, f, indent=2)
        logger.info("saved_production_baseline", path=str(target_file_path))
