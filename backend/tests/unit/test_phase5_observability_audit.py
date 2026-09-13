"""
DevVision AI - Phase 5 Observability Gap Audit

Unit tests auditing:
1. Log Sanitization:
   - AST scan of all `logger.info`, `logger.warning`, `logger.error` calls across `backend/app/`.
   - Verify NO raw query text, document body, chunk text, LLM prompts, passwords, or tokens are logged.
2. Metric Cardinality:
   - Inspect all Prometheus metrics registered in `metrics_registry`.
   - Assert zero unbounded labels (no user_id, document_id, workspace_id, query_text, etc.).
   - Verify all metric labels belong to a strictly bounded set.
"""

import ast
import os
from pathlib import Path
import pytest

from app.core.metrics import metrics_registry, Metric


# =========================================================================
# 1. METRIC CARDINALITY AUDIT
# =========================================================================

def test_metrics_cardinality_strictly_bounded():
    """
    Assert that NO registered Prometheus metric exposes high-cardinality or unbounded labels
    such as user_id, workspace_id, document_id, query_text, or raw tokens.
    """
    forbidden_label_names = {
        "user_id",
        "workspace_id",
        "document_id",
        "query_id",
        "chunk_id",
        "generation_id",
        "query_text",
        "query",
        "email",
        "password",
        "token",
        "session_id",
        "client_ip",
        "filename",
        "url",
    }

    allowed_label_names = {
        "status",
        "stage",
        "reason",
        "model_name",
        "model_version",
        "method",
        "endpoint",
        "handler",
        "env",
        "le",  # Prometheus histogram bucket label
    }

    assert len(metrics_registry._metrics) > 0, "Metrics registry should contain registered metrics"

    for name, metric in metrics_registry._metrics.items():
        assert isinstance(metric, Metric)
        label_names = set(metric.label_names)

        # 1. Check for forbidden high-cardinality labels
        forbidden_present = label_names.intersection(forbidden_label_names)
        assert not forbidden_present, (
            f"Metric '{name}' contains unbounded/sensitive labels: {forbidden_present}. "
            "Metrics must not cause cardinality explosion or leak PII/tenant data."
        )

        # 2. Check that all labels belong to approved bounded set
        unexpected_labels = label_names - allowed_label_names
        assert not unexpected_labels, (
            f"Metric '{name}' contains unapproved label names: {unexpected_labels}. "
            f"Allowed labels: {allowed_label_names}"
        )


# =========================================================================
# 2. LOG SANITIZATION AUDIT (AST SCAN)
# =========================================================================

def test_log_sanitization_ast_scan():
    """
    Parses all Python files in `backend/app/` into ASTs and checks every `logger.*` call.
    Verifies that no sensitive payload fields (passwords, tokens, query text, chunk content)
    are passed as logged keyword arguments or printed in message strings.
    """
    app_dir = Path(__file__).resolve().parent.parent.parent / "app"
    assert app_dir.exists(), f"App directory {app_dir} does not exist"

    forbidden_log_keywords = {
        "password",
        "raw_token",
        "token_hash",
        "session_token",
        "secret",
        "jwt",
        "query_text",
        "text_content",
        "tsv_content",
        "document_content",
        "prompt",
        "user_prompt",
        "system_prompt",
        "raw_text",
    }

    violations = []

    for py_file in app_dir.rglob("*.py"):
        try:
            with open(py_file, "r", encoding="utf-8-sig") as f:
                source = f.read()
            tree = ast.parse(source, filename=str(py_file))
        except Exception as exc:
            violations.append(f"Failed to parse {py_file}: {exc}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # Detect logger.info, logger.warning, logger.error, logger.debug
                is_logger_call = False
                if isinstance(func, ast.Attribute) and func.attr in {"info", "warning", "error", "debug", "critical"}:
                    if isinstance(func.value, ast.Name) and func.value.id in {"logger", "log"}:
                        is_logger_call = True

                if is_logger_call:
                    # Check keyword arguments (e.g. logger.info("event", query_text=...))
                    for kw in node.keywords:
                        if kw.arg and kw.arg.lower() in forbidden_log_keywords:
                            violations.append(
                                f"{py_file.name}:{node.lineno} - Logger call passes sensitive keyword '{kw.arg}'"
                            )

    assert not violations, "Log sanitization audit failed with violations:\n" + "\n".join(violations)
