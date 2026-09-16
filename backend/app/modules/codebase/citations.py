import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

# Regex to capture [SNIPPET_1], [SNIPPET_2] or [1], [2]
CODE_CITATION_MARKER_PATTERN = re.compile(r"\[(?:SNIPPET_)?(\d+)\]", re.IGNORECASE)

REFUSAL_PHRASES = [
    "i cannot answer",
    "i cannot find",
    "i do not have enough information",
    "the provided codebase does not contain",
    "there is no information",
    "not mentioned in the indexed codebase",
    "unable to answer",
]


@dataclass
class CodeCitationMatch:
    marker_index: int
    raw_marker: str


@dataclass
class CodeValidationResult:
    is_grounded: bool
    sanitized_answer: str
    valid_citations: List[int]
    stripped_markers: List[str]
    is_refusal: bool


class CodeCitationValidator:
    @classmethod
    def validate_and_filter(
        cls,
        answer_text: str,
        retrieved_chunk_count: int,
    ) -> CodeValidationResult:
        lower = answer_text.lower()
        if any(phrase in lower for phrase in REFUSAL_PHRASES):
            return CodeValidationResult(
                is_grounded=True,
                sanitized_answer=answer_text,
                valid_citations=[],
                stripped_markers=[],
                is_refusal=True,
            )

        valid_citations: Set[int] = set()
        stripped_markers: List[str] = []

        def _replace_marker(match: re.Match) -> str:
            raw = match.group(0)
            idx = int(match.group(1))
            if 1 <= idx <= retrieved_chunk_count:
                valid_citations.add(idx)
                return raw
            else:
                # Invalid or invented marker outside retrieved set
                stripped_markers.append(raw)
                return ""

        cleaned_text = CODE_CITATION_MARKER_PATTERN.sub(_replace_marker, answer_text)

        # If answer had no citations at all or only invalid ones, but asserts claims,
        # flag grounded status
        is_grounded = len(valid_citations) > 0 or len(answer_text.strip()) < 50

        return CodeValidationResult(
            is_grounded=is_grounded,
            sanitized_answer=cleaned_text.strip(),
            valid_citations=sorted(list(valid_citations)),
            stripped_markers=stripped_markers,
            is_refusal=False,
        )
