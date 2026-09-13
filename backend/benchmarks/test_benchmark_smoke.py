"""
DevVision AI - Phase 5 Benchmark Smoke Test

Runs a fast, low-concurrency performance benchmark to verify that:
1. Retrieval and RAG queries complete without errors.
2. Error rate is 0.0% and Timeout rate is 0.0%.
3. End-to-end P50 latency is within acceptable threshold (< 2000 ms).
4. Structured JSON benchmark report is generated in results directory.
"""

import os
from pathlib import Path
import pytest
from benchmarks.load_test import BenchmarkRunner
from benchmarks.conftest import BenchmarkTestingSessionLocal, benchmark_test_engine
from app.core.database import Base


@pytest.mark.asyncio
async def test_rag_benchmark_smoke(tmp_path):
    """
    CI smoke benchmark running a low-concurrency test to ensure
    performance characteristics and retrieval pipeline don't regress.
    """
    async with benchmark_test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    runner = BenchmarkRunner(
        concurrency=2,
        total_queries=6,
        docs_per_workspace=2,
        distribution="uniform",
        output_dir=str(tmp_path),
        use_mock_rag=True,
        session_factory=BenchmarkTestingSessionLocal,
    )

    report = await runner.run()

    # Assertions
    traffic = report["traffic"]
    assert traffic["total_queries"] == 6
    assert traffic["successful_queries"] == 6
    assert traffic["error_rate_pct"] == 0.0, "Smoke benchmark must have zero errors"
    assert traffic["timeout_rate_pct"] == 0.0, "Smoke benchmark must have zero timeouts"

    latency = report["latency_ms"]
    assert latency["end_to_end_rag"]["p50"] > 0.0
    assert latency["end_to_end_rag"]["p50"] < 2000.0, "P50 latency exceeded 2000ms threshold"

    # Verify JSON file was written
    saved_files = list(tmp_path.glob("benchmark_report_*.json"))
    assert len(saved_files) >= 1
