"""
DevVision AI - Pure-Python Prometheus Metrics Registry.

Zero-dependency, thread-safe metrics collector producing valid Prometheus/OpenMetrics
exposition format for RAG pipeline and worker operations.
"""

import threading
import time
from typing import Dict, List, Optional, Tuple


class Metric:
    def __init__(self, name: str, description: str, metric_type: str, label_names: Optional[List[str]] = None):
        self.name = name
        self.description = description
        self.metric_type = metric_type
        self.label_names = tuple(sorted(label_names)) if label_names else ()
        self._lock = threading.Lock()

    def _format_labels(self, labels: Dict[str, str]) -> str:
        if not labels:
            return ""
        items = [f'{k}="{v}"' for k, v in sorted(labels.items())]
        return "{" + ",".join(items) + "}"


class Counter(Metric):
    def __init__(self, name: str, description: str, label_names: Optional[List[str]] = None):
        super().__init__(name, description, "counter", label_names)
        self._values: Dict[Tuple[Tuple[str, str], ...], float] = {}

    def inc(self, amount: float = 1.0, **labels):
        if amount < 0:
            raise ValueError("Counter cannot be decremented")
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def collect(self) -> List[str]:
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} counter",
        ]
        with self._lock:
            if not self._values:
                lines.append(f"{self.name} 0")
            else:
                for key, val in sorted(self._values.items()):
                    lbls = dict(key)
                    lbl_str = self._format_labels(lbls)
                    lines.append(f"{self.name}{lbl_str} {val}")
        return lines


class Gauge(Metric):
    def __init__(self, name: str, description: str, label_names: Optional[List[str]] = None):
        super().__init__(name, description, "gauge", label_names)
        self._values: Dict[Tuple[Tuple[str, str], ...], float] = {}

    def set(self, value: float, **labels):
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] = float(value)

    def inc(self, amount: float = 1.0, **labels):
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def dec(self, amount: float = 1.0, **labels):
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) - amount

    def collect(self) -> List[str]:
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} gauge",
        ]
        with self._lock:
            if not self._values:
                lines.append(f"{self.name} 0")
            else:
                for key, val in sorted(self._values.items()):
                    lbls = dict(key)
                    lbl_str = self._format_labels(lbls)
                    lines.append(f"{self.name}{lbl_str} {val}")
        return lines


class Histogram(Metric):
    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)

    def __init__(
        self,
        name: str,
        description: str,
        label_names: Optional[List[str]] = None,
        buckets: Optional[Tuple[float, ...]] = None,
    ):
        super().__init__(name, description, "histogram", label_names)
        b = sorted(buckets or self.DEFAULT_BUCKETS)
        self.buckets = tuple(b)
        # key -> (bucket_counts: Dict[float, int], sum: float, count: int)
        self._samples: Dict[Tuple[Tuple[str, str], ...], Tuple[Dict[float, int], float, int]] = {}

    def observe(self, amount: float, **labels):
        key = tuple(sorted(labels.items()))
        with self._lock:
            if key not in self._samples:
                b_counts = {b: 0 for b in self.buckets}
                self._samples[key] = (b_counts, 0.0, 0)
            b_counts, current_sum, count = self._samples[key]
            for b in self.buckets:
                if amount <= b:
                    b_counts[b] += 1
            self._samples[key] = (b_counts, current_sum + amount, count + 1)

    def time(self, **labels):
        return HistogramTimer(self, labels)

    def collect(self) -> List[str]:
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} histogram",
        ]
        with self._lock:
            if not self._samples:
                for b in self.buckets:
                    lines.append(f'{self.name}_bucket{{le="{b}"}} 0')
                lines.append(f'{self.name}_bucket{{le="+Inf"}} 0')
                lines.append(f"{self.name}_count 0")
                lines.append(f"{self.name}_sum 0.0")
            else:
                for key, (b_counts, current_sum, count) in sorted(self._samples.items()):
                    lbls = dict(key)
                    # Bucket lines with le
                    for b in self.buckets:
                        merged = dict(lbls)
                        merged["le"] = str(b)
                        lines.append(f"{self.name}_bucket{self._format_labels(merged)} {b_counts[b]}")
                    # +Inf bucket line equals total count
                    merged_inf = dict(lbls)
                    merged_inf["le"] = "+Inf"
                    lines.append(f"{self.name}_bucket{self._format_labels(merged_inf)} {count}")
                    # Sum and Count
                    lines.append(f"{self.name}_count{self._format_labels(lbls)} {count}")
                    lines.append(f"{self.name}_sum{self._format_labels(lbls)} {current_sum:.6f}")
        return lines


class HistogramTimer:
    def __init__(self, histogram: Histogram, labels: Dict[str, str]):
        self.histogram = histogram
        self.labels = labels
        self.start = 0.0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.perf_counter() - self.start
        self.histogram.observe(duration, **self.labels)


class MetricsRegistry:
    """Thread-safe global registry for all application Prometheus metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._metrics: Dict[str, Metric] = {}

    def register_counter(self, name: str, description: str, label_names: Optional[List[str]] = None) -> Counter:
        with self._lock:
            if name in self._metrics:
                metric = self._metrics[name]
                if not isinstance(metric, Counter):
                    raise TypeError(f"Metric {name} already registered as {type(metric)}")
                return metric
            c = Counter(name, description, label_names)
            self._metrics[name] = c
            return c

    def register_gauge(self, name: str, description: str, label_names: Optional[List[str]] = None) -> Gauge:
        with self._lock:
            if name in self._metrics:
                metric = self._metrics[name]
                if not isinstance(metric, Gauge):
                    raise TypeError(f"Metric {name} already registered as {type(metric)}")
                return metric
            g = Gauge(name, description, label_names)
            self._metrics[name] = g
            return g

    def register_histogram(
        self,
        name: str,
        description: str,
        label_names: Optional[List[str]] = None,
        buckets: Optional[Tuple[float, ...]] = None,
    ) -> Histogram:
        with self._lock:
            if name in self._metrics:
                metric = self._metrics[name]
                if not isinstance(metric, Histogram):
                    raise TypeError(f"Metric {name} already registered as {type(metric)}")
                return metric
            h = Histogram(name, description, label_names, buckets)
            self._metrics[name] = h
            return h

    def generate_exposition(self) -> str:
        """Renders exact Prometheus exposition format."""
        with self._lock:
            metrics_list = list(self._metrics.values())
        output_lines: List[str] = []
        for metric in metrics_list:
            output_lines.extend(metric.collect())
        return "\n".join(output_lines) + "\n"

    def reset_all(self):
        """Clears all metric values (used in test fixtures)."""
        with self._lock:
            for metric in self._metrics.values():
                with metric._lock:
                    if hasattr(metric, "_values"):
                        metric._values.clear()
                    if hasattr(metric, "_samples"):
                        metric._samples.clear()


# Global Singleton Registry
metrics_registry = MetricsRegistry()

# Pre-registered Core RAG & Worker Metrics
rag_query_total = metrics_registry.register_counter(
    "rag_query_total",
    "Total RAG queries executed by outcome status",
    ["status"],
)
rag_query_duration_seconds = metrics_registry.register_histogram(
    "rag_query_duration_seconds",
    "Total RAG query end-to-end execution duration in seconds",
)
rag_dense_retrieval_duration_seconds = metrics_registry.register_histogram(
    "rag_dense_retrieval_duration_seconds",
    "Duration of dense vector retrieval in seconds",
)
rag_sparse_retrieval_duration_seconds = metrics_registry.register_histogram(
    "rag_sparse_retrieval_duration_seconds",
    "Duration of sparse full-text retrieval in seconds",
)
rag_rerank_duration_seconds = metrics_registry.register_histogram(
    "rag_rerank_duration_seconds",
    "Duration of cross-encoder reranking in seconds",
)
rag_llm_generation_duration_seconds = metrics_registry.register_histogram(
    "rag_llm_generation_duration_seconds",
    "Duration of local LLM answer generation in seconds",
)
rag_citation_validation_failures_total = metrics_registry.register_counter(
    "rag_citation_validation_failures_total",
    "Total citation validation check failures by reason",
    ["reason"],
)
rag_safe_refusals_total = metrics_registry.register_counter(
    "rag_safe_refusals_total",
    "Total RAG queries resulting in safe refusal due to insufficient context",
)

# Worker Ingestion Metrics
rag_documents_ingested_total = metrics_registry.register_counter(
    "rag_documents_ingested_total",
    "Total documents processed by outcome status",
    ["status"],
)
rag_ingestion_failures_total = metrics_registry.register_counter(
    "rag_ingestion_failures_total",
    "Total ingestion failures by failure stage",
    ["stage"],
)
rag_ingestion_duration_seconds = metrics_registry.register_histogram(
    "rag_ingestion_duration_seconds",
    "Total duration of document ingestion and indexing in seconds",
)
rag_chunks_created_total = metrics_registry.register_counter(
    "rag_chunks_created_total",
    "Total text chunks created and indexed",
)
rag_embeddings_created_total = metrics_registry.register_counter(
    "rag_embeddings_created_total",
    "Total dense vector embeddings generated",
)
rag_lease_acquisition_failures_total = metrics_registry.register_counter(
    "rag_lease_acquisition_failures_total",
    "Total document processing lease acquisition rejections by reason",
    ["reason"],
)
rag_stale_worker_rejections_total = metrics_registry.register_counter(
    "rag_stale_worker_rejections_total",
    "Total stale worker mutation rejections by fencing ownership barrier",
)
rag_generation_activation_total = metrics_registry.register_counter(
    "rag_generation_activation_total",
    "Total index generations successfully activated",
)
rag_generation_failures_total = metrics_registry.register_counter(
    "rag_generation_failures_total",
    "Total candidate index generations marked failed",
    ["reason"],
)
rag_generation_gc_total = metrics_registry.register_counter(
    "rag_generation_gc_total",
    "Total retired or failed index generations cleaned up by GC",
)
