"""
DevVision AI - Evaluation Dataset Loader.

Loads, validates, and filters evaluation benchmark datasets.
Supports filtering by:
- Category (factual_lookup, multi_chunk_reasoning, negation, etc.)
- Difficulty (easy, medium, hard)
- Tags
- Workspace ID
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
import structlog

from evaluation.models import (
    CaseCategory,
    CaseDifficulty,
    EvaluationCase,
    EvaluationDataset,
)

logger = structlog.get_logger(__name__)


def load_dataset(
    file_path: Union[str, Path] if "Union" in globals() else Any,
    categories: Optional[List[CaseCategory]] = None,
    difficulties: Optional[List[CaseDifficulty]] = None,
    tags: Optional[List[str]] = None,
    workspace_id: Optional[str] = None,
) -> EvaluationDataset:
    """
    Loads an evaluation dataset from JSON with validation and filtering.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Evaluation dataset file not found: {file_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    name = data.get("name", "Unknown Dataset")
    version = data.get("version", "1.0.0")
    description = data.get("description", "")
    created_at = data.get("created_at", "")

    raw_cases = data.get("cases", [])
    cases: List[EvaluationCase] = []

    cat_set = set(categories) if categories else None
    diff_set = set(difficulties) if difficulties else None
    tag_set = set(tags) if tags else None

    for raw in raw_cases:
        case_id = raw.get("case_id")
        query = raw.get("query")
        if not case_id or not query:
            logger.warning("skipping_invalid_case", raw=raw)
            continue

        raw_cat = raw.get("category", "factual_lookup")
        try:
            cat = CaseCategory(raw_cat)
        except ValueError:
            cat = CaseCategory.FACTUAL_LOOKUP

        raw_diff = raw.get("difficulty", "medium")
        try:
            diff = CaseDifficulty(raw_diff)
        except ValueError:
            diff = CaseDifficulty.MEDIUM

        case_tags = raw.get("tags", [])
        case_ws = raw.get("target_workspace_id")

        # Filters
        if cat_set and cat not in cat_set:
            continue
        if diff_set and diff not in diff_set:
            continue
        if tag_set and not tag_set.intersection(set(case_tags)):
            continue
        if workspace_id and case_ws and case_ws != workspace_id:
            continue

        cases.append(
            EvaluationCase(
                case_id=case_id,
                query=query,
                expected_document_ids=raw.get("expected_document_ids", []),
                expected_chunk_ids=raw.get("expected_chunk_ids", []),
                expected_facts=raw.get("expected_facts", []),
                negative_document_ids=raw.get("negative_document_ids", []),
                negative_chunk_ids=raw.get("negative_chunk_ids", []),
                category=cat,
                difficulty=diff,
                tags=case_tags,
                description=raw.get("description", ""),
                target_workspace_id=case_ws,
                adversarial_payload=raw.get("adversarial_payload"),
            )
        )

    return EvaluationDataset(
        name=name,
        version=version,
        description=description,
        created_at=created_at,
        cases=cases,
    )
