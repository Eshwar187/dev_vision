"""
DevVision AI - Citation Validator and Remediation Engine.

Enforces strict provenance validation on LLM output sentences against retrieved context.
Taxonomy:
- valid: Sentence has citations and passes claim support threshold against cited passages.
- invalid_marker: Sentence references markers not in the provided retrieved context (e.g. [99] when top 5 retrieved).
- missing_citation: Assertive sentence has no citation markers.
- unsupported_claim: Sentence has citation markers, but claimed content lacks lexical/semantic grounding.

Exemptions:
- Non-assertive sentences (headings, markdown bullet lists, code blocks, refusal statements).
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

# Regex to capture [1], [2], [1, 2], [1][2] citation markers
CITATION_MARKER_PATTERN = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

# Refusal prefixes that do not require citations
REFUSAL_PHRASES = [
    "i cannot find",
    "i do not have enough information",
    "the provided documents do not contain",
    "there is no information",
    "not mentioned in the provided context",
    "based on the provided documents, there is no",
    "i am unable to answer",
]


@dataclass
class SentenceValidationResult:
    sentence: str
    status: str  # "valid", "invalid_marker", "missing_citation", "unsupported_claim", "exempt"
    markers: List[int]
    unsupported_reason: Optional[str] = None


@dataclass
class ValidationReport:
    is_valid: bool
    sentences: List[SentenceValidationResult]
    has_unverified_claims: bool
    remediation_prompt: Optional[str] = None


class CitationValidator:
    """
    Validates LLM generated answers against retrieved context chunks.
    Ensures every factual claim is strictly supported by cited source excerpts.
    """

    def __init__(self, lexical_overlap_threshold: float = 0.25):
        self.overlap_threshold = lexical_overlap_threshold

    def is_exempt_sentence(self, sentence: str) -> bool:
        """Check if sentence is structural/non-assertive or a refusal."""
        stripped = sentence.strip()
        if not stripped:
            return True

        # Headings (# Title, ## Subheading)
        if stripped.startswith("#"):
            return True

        # Markdown bullet or list item prefix without substantive assertion
        if re.match(r"^[-*+]\s*$", stripped) or re.match(r"^\d+\.\s*$", stripped):
            return True

        # Code block fences or indented code
        if stripped.startswith("```") or stripped.endswith("```"):
            return True

        # Refusal statements
        lower = stripped.lower()
        if any(phrase in lower for phrase in REFUSAL_PHRASES):
            return True

        # Very short greetings or transitions
        if len(stripped.split()) <= 3 and stripped.endswith(":"):
            return True

        return False

    def split_sentences(self, text: str) -> List[str]:
        """
        Split text into logical sentences while preserving citation markers and formatting.
        Handles newlines and periods followed by spaces.
        """
        # First split by paragraphs/lines
        lines = text.split("\n")
        sentences: List[str] = []
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue
            if self.is_exempt_sentence(trimmed):
                sentences.append(trimmed)
                continue

            # Split on sentence terminals (.!?) followed by space or end
            parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\[])", trimmed)
            for p in parts:
                p_clean = p.strip()
                if p_clean:
                    sentences.append(p_clean)

        return sentences

    def extract_markers(self, sentence: str) -> List[int]:
        """Extract all integer citation markers like [1], [2, 3] from a sentence."""
        matches = CITATION_MARKER_PATTERN.findall(sentence)
        markers: Set[int] = set()
        for match in matches:
            for item in match.split(","):
                item_str = item.strip()
                if item_str.isdigit():
                    markers.add(int(item_str))
        return sorted(list(markers))

    def _calculate_lexical_overlap(self, sentence_words: Set[str], context_words: Set[str]) -> float:
        """Compute Jaccard-like content word overlap excluding stopwords."""
        stopwords = {
            "a", "an", "the", "and", "or", "but", "if", "in", "on", "at", "to", "for",
            "with", "by", "of", "from", "as", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "can", "could", "shall",
            "should", "will", "would", "may", "might", "must", "it", "its", "this", "that",
            "these", "those", "they", "them", "their", "we", "our", "you", "your", "he",
            "she", "him", "her", "which", "what", "where", "when", "how", "all", "any", "both"
        }
        filtered_sentence = {w for w in sentence_words if w not in stopwords and len(w) > 2}
        if not filtered_sentence:
            return 1.0  # Trivial sentence
        overlap = filtered_sentence.intersection(context_words)
        return len(overlap) / len(filtered_sentence)

    def validate(
        self,
        answer: str,
        retrieved_contexts: Dict[int, str],  # Dict mapping marker_int (e.g. 1, 2) to passage content
    ) -> ValidationReport:
        """
        Validate generated answer against retrieved context excerpts.
        """
        sentences = self.split_sentences(answer)
        results: List[SentenceValidationResult] = []
        has_violations = False
        unsupported_sentences: List[str] = []

        valid_marker_ids = set(retrieved_contexts.keys())

        for sent in sentences:
            if self.is_exempt_sentence(sent):
                results.append(SentenceValidationResult(sentence=sent, status="exempt", markers=[]))
                continue

            markers = self.extract_markers(sent)
            if not markers:
                # Assertive sentence with NO citation marker
                results.append(
                    SentenceValidationResult(
                        sentence=sent,
                        status="missing_citation",
                        markers=[],
                        unsupported_reason="Sentence makes an assertion without citing any source passage.",
                    )
                )
                has_violations = True
                unsupported_sentences.append(sent)
                continue

            # Check for invalid markers (referencing IDs not in retrieved context)
            invalid = [m for m in markers if m not in valid_marker_ids]
            if invalid:
                results.append(
                    SentenceValidationResult(
                        sentence=sent,
                        status="invalid_marker",
                        markers=markers,
                        unsupported_reason=f"Cites nonexistent marker(s): {invalid}. Available: {sorted(list(valid_marker_ids))}",
                    )
                )
                has_violations = True
                unsupported_sentences.append(sent)
                continue

            # Grounding check: verify that cited text actually supports the sentence content
            cited_text = " ".join([retrieved_contexts[m] for m in markers]).lower()
            context_words = set(re.findall(r"\b\w+\b", cited_text))
            
            clean_sent = re.sub(CITATION_MARKER_PATTERN, "", sent).lower()
            sent_words = set(re.findall(r"\b\w+\b", clean_sent))

            overlap_ratio = self._calculate_lexical_overlap(sent_words, context_words)
            if overlap_ratio < self.overlap_threshold:
                results.append(
                    SentenceValidationResult(
                        sentence=sent,
                        status="unsupported_claim",
                        markers=markers,
                        unsupported_reason=f"Claim overlap ({overlap_ratio:.2f}) below grounding threshold ({self.overlap_threshold:.2f}).",
                    )
                )
                has_violations = True
                unsupported_sentences.append(sent)
            else:
                results.append(
                    SentenceValidationResult(
                        sentence=sent,
                        status="valid",
                        markers=markers,
                    )
                )

        remediation_prompt: Optional[str] = None
        if has_violations:
            violation_details = "\n".join([f"- \"{s}\"" for s in unsupported_sentences[:3]])
            remediation_prompt = (
                "Your previous response contained claims that either lacked citations, cited invalid sources, "
                "or could not be verified directly from the provided passages:\n"
                f"{violation_details}\n"
                "Please rewrite your answer ensuring EVERY factual sentence has a valid citation [n] matching "
                "the passages exactly, or explicitly state that the information is not provided in the documents."
            )

        return ValidationReport(
            is_valid=not has_violations,
            sentences=results,
            has_unverified_claims=has_violations,
            remediation_prompt=remediation_prompt,
        )
