# DevVision AI — Phase 6: RAG Quality Evaluation & Production Acceptance

## 1. Overview & Objectives

Phase 6 implements a rigorous evaluation, benchmarking, and production acceptance layer for the self-hosted DevVision AI RAG system. It proves empirically and reproducibly that:
1. Retrieval reliably surfaces the correct evidence across diverse query categories.
2. Cross-Encoder reranking significantly lifts retrieval quality over raw dense or sparse search.
3. Generated responses are strictly grounded in retrieved evidence, with sentence-level citation verification and semantic contradiction detection.
4. Security and isolation boundaries (multi-tenant workspace isolation, prompt injection defenses, stale generation shielding) remain impenetrable.
5. Performance and quality do not regress across pipeline revisions.

---

## 2. Benchmark Dataset Architecture

The benchmark dataset is located at:
```
backend/evaluation/datasets/curated_benchmark.json
```

It contains 40 curated evaluation cases covering 7 primary challenge categories:
- **`factual_lookup`**: Exact fact retrieval across configuration limits, architecture invariants, and algorithms.
- **`multi_chunk_reasoning`**: Queries requiring synthesis across multiple chunks and documents.
- **`negation`**: Negative phrasing and policy questions (e.g. access prohibitions, absence of external cloud AI).
- **`entity_inversion`**: Queries containing swapped entity pairs or inverted relationships.
- **`prompt_injection`**: Delimiter escape attempts, `<system>` tag injection, and markdown mimicry.
- **`cross_tenant_isolation`**: Cross-workspace extraction attempts targeting foreign tenant secrets.
- **`empty_retrieval`**: Out-of-corpus queries requiring safe model refusal without hallucination.

Each case specifies:
- `query`: The evaluation question.
- `expected_document_ids` & `expected_chunk_ids`: Ground-truth evidence targets.
- `expected_facts`: Normalized factual assertions required in the answer.
- `negative_document_ids` & `negative_chunk_ids`: Prohibited targets (used for leakage testing).
- `category`, `difficulty`, and `tags`.

---

## 3. Retrieval Ablation Engine

The ablation engine (`backend/evaluation/ablation.py`) runs queries across four distinct configurations under identical conditions:
1. **Dense Only**: Semantic search using `pgvector` HNSW index with cosine distance (`<=>`).
2. **Sparse Only**: Lexical full-text search using PostgreSQL `tsvector` with `ts_rank` and GIN index.
3. **Hybrid RRF**: Reciprocal Rank Fusion ($k=60$) combining dense and sparse pools.
4. **Hybrid RRF + Reranker**: Top 20 candidate chunks from RRF re-evaluated using the self-hosted BGE Cross-Encoder.

### Pure-Python Ranking Metrics
All ranking metrics are computed mathematically without third-party dependencies (`backend/evaluation/metrics.py`):
- **Recall@K** ($K \in \{1, 3, 5, 10\}$): Fraction of relevant items retrieved in top $K$.
- **Precision@K**: Density of relevant items in top $K$.
- **MRR (Mean Reciprocal Rank)**: $\frac{1}{|Q|} \sum_{q} \frac{1}{\text{rank}_q}$.
- **NDCG@K**: Normalized Discounted Cumulative Gain with binary relevance.
- **HitRate@K**: Proportion of queries where at least one relevant document was in top $K$.
- **Percentile Latencies**: P50, P95, and P99 latency tracking.

---

## 4. Grounding & Citation Quality Evaluator

The citation evaluator (`backend/evaluation/citations.py`) assesses generated answers against retrieved passages:
- **Citation Precision**: $\frac{\text{Supported Sentences with Citations}}{\text{Total Sentences with Citations}}$.
- **Citation Recall**: Fraction of expected facts present and verified by citations.
- **Unsupported Claim Rate**: Proportion of assertive sentences lacking supporting evidence.
- **Invalid Marker Rate**: Bracket markers `[N]` that reference non-existent context excerpts.
- **Semantic Contradiction Rate**: Employs structural negation and polarity analysis (`detect_semantic_inversion`) to catch models claiming the opposite of passage facts.

---

## 5. Production Acceptance Gates

The acceptance evaluator (`backend/evaluation/acceptance.py`) enforces strict, non-negotiable gates:

| Gate Metric | Condition | Production Target |
| :--- | :---: | :---: |
| `retrieval_recall_at_5` | $\ge$ | **80.0%** |
| `retrieval_mrr` | $\ge$ | **0.70** |
| `retrieval_ndcg_at_5` | $\ge$ | **0.75** |
| `citation_precision` | $\ge$ | **90.0%** |
| `unsupported_claim_rate` | $\le$ | **10.0%** |
| `cross_tenant_leak_rate` | $==$ | **0.0%** |
| `prompt_injection_escape_rate` | $==$ | **0.0%** |
| `stale_generation_leak_rate` | $==$ | **0.0%** |

### Baseline Regression Invariants
- Evaluates against `backend/evaluation/baselines/baseline_phase6.json`.
- Fails if retrieval or citation metrics degrade by $> 5\%$ relative to baseline.
- Fails if P95 latency regresses by $> 20\%$.
- **Immutability Invariant**: A failing run NEVER modifies or updates the stored baseline file. Updates require the explicit CLI flag `--write-baseline`.

---

## 6. CLI Usage & Automated Reporting

### Running Evaluation Against Active PostgreSQL / Supabase:
```bash
python -m evaluation.runner --check-acceptance
```

### Running Evaluation in Fast In-Memory Mode (CI / Offline):
```bash
python -m evaluation.runner --in-memory --check-acceptance
```

### Explicitly Updating the Versioned Baseline:
```bash
python -m evaluation.runner --write-baseline
```

### Generated Artifacts:
- `backend/evaluation/results/evaluation_report.json`: Machine-readable JSON summary.
- `backend/evaluation/results/latest_report.md`: Human-readable Markdown summary with tables and delta charts.
