"""
DevVision AI - Citation and Grounding Evaluation Engine.

Measures:
- Citation Precision: Fraction of citations that actually support the sentence they are attached to.
- Citation Recall: Fraction of claimed facts in the response that have valid supporting citations.
- Unsupported Claim Rate: Fraction of assertive sentences lacking grounding.
- Invalid Marker Rate: Citations referencing markers not in retrieved context.
- Missing Citation Rate: Assertive sentences with no citations.
- Semantic Contradiction Rate: Detects negation/polarity inversion (e.g. "is enabled" vs "is NOT enabled")
  where lexical overlap is high but semantic meaning differs.

Explicitly distinguishes:
A. Lexical grounding (n-gram/token overlap heuristic).
B. Semantic correctness (contradiction/inversion detection).
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple
import structlog

from app.modules.rag.citations import CitationValidator, CITATION_MARKER_PATTERN, REFUSAL_PHRASES
from evaluation.models import CitationMetricsResult

logger = structlog.get_logger(__name__)

# Common English negation indicators
NEGATION_TOKENS = {"not", "never", "no", "cannot", "isn't", "aren't", "wasn't", "weren't", "neither", "nor", "disabled", "disallowed", "prohibited", "prevented"}


class CitationEvaluator:
    """
    Evaluates grounding quality and citation validity of generated answers against context.
    """

    def __init__(self, validator: Optional[CitationValidator] = None):
        self.validator = validator or CitationValidator()

    def detect_semantic_inversion(
        self, claim_sentence: str, context_text: str
    ) -> bool:
        """
        Detects if a claim sentence flips the polarity (negation) of the context statement.
        Example:
            context: "The feature flag is not enabled by default."
            claim: "The feature flag is enabled by default [1]." -> Inverted!
            context: "Authentication is required."
            claim: "Authentication is not required [1]." -> Inverted!
        """
        clean_claim = re.sub(CITATION_MARKER_PATTERN, "", claim_sentence).lower()
        clean_context = context_text.lower()

        # Token sets
        claim_words = set(re.findall(r"\b[a-z0-9_-]+\b", clean_claim))
        context_words = set(re.findall(r"\b[a-z0-9_-]+\b", clean_context))

        claim_has_negation = bool(claim_words.intersection(NEGATION_TOKENS))
        context_has_negation = bool(context_words.intersection(NEGATION_TOKENS))

        # If polarities differ while non-negation content overlap is very high (> 60%), flag semantic inversion
        non_neg_claim = claim_words - NEGATION_TOKENS
        non_neg_context = context_words - NEGATION_TOKENS

        if non_neg_claim and non_neg_context:
            overlap = len(non_neg_claim.intersection(non_neg_context)) / float(len(non_neg_claim))
            if overlap >= 0.50 and (claim_has_negation != context_has_negation):
                return True

        return False

    def evaluate_response(
        self,
        generated_answer: str,
        retrieved_passages: List[Dict[str, Any]],  # [{"marker": 1, "content": "..."}]
        expected_facts: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluates a single answer.
        Returns detailed sentence breakdown, citation counts, and polarity checks.
        """
        # Build marker to content mapping
        marker_map = {}
        for p in retrieved_passages:
            marker_num = p.get("citation_marker") or p.get("marker")
            if marker_num is not None:
                marker_map[int(marker_num)] = p.get("content", "")

        report = self.validator.validate(generated_answer, marker_map)

        total_sentences = 0
        valid_sentences = 0
        unsupported_sentences = 0
        missing_citation_sentences = 0
        invalid_marker_sentences = 0
        semantic_inversions = 0
        total_citations = 0
        valid_citations = 0

        for s in report.sentences:
            if s.status == "exempt":
                continue

            total_sentences += 1
            total_citations += len(s.markers)

            if s.status == "valid":
                valid_sentences += 1
                valid_citations += len(s.markers)

                # Further inspect valid lexical sentences for semantic contradiction/inversion
                cited_text = " ".join(marker_map.get(m, "") for m in s.markers)
                if self.detect_semantic_inversion(s.sentence, cited_text):
                    semantic_inversions += 1
                    # Downgrade valid status if semantically inverted
                    s.status = "unsupported_claim"
                    s.unsupported_reason = "Semantic polarity inversion detected (negation mismatch)."
                    valid_sentences -= 1
                    valid_citations -= len(s.markers)
                    unsupported_sentences += 1
            elif s.status == "unsupported_claim":
                unsupported_sentences += 1
            elif s.status == "missing_citation":
                missing_citation_sentences += 1
            elif s.status == "invalid_marker":
                invalid_marker_sentences += 1

        # Check citation recall against expected facts if provided
        fact_recall_score = 1.0
        if expected_facts:
            matched_facts = 0
            for fact in expected_facts:
                fact_lower = fact.lower()
                # Check if fact is mentioned in any valid sentence
                for s in report.sentences:
                    if s.status == "valid" and fact_lower in s.sentence.lower():
                        matched_facts += 1
                        break
            fact_recall_score = matched_facts / float(len(expected_facts))

        return {
            "total_sentences": total_sentences,
            "valid_sentences": valid_sentences,
            "unsupported_sentences": unsupported_sentences,
            "missing_citation_sentences": missing_citation_sentences,
            "invalid_marker_sentences": invalid_marker_sentences,
            "semantic_inversions": semantic_inversions,
            "total_citations": total_citations,
            "valid_citations": valid_citations,
            "fact_recall_score": fact_recall_score,
            "sentences": report.sentences,
        }

    def aggregate_citation_metrics(
        self, evaluations: List[Dict[str, Any]]
    ) -> CitationMetricsResult:
        """
        Computes overall citation metrics across a batch of query evaluations.
        """
        if not evaluations:
            return CitationMetricsResult()

        total_sent = sum(e["total_sentences"] for e in evaluations)
        total_cits = sum(e["total_citations"] for e in evaluations)
        valid_cits = sum(e["valid_citations"] for e in evaluations)
        unsupp_sent = sum(e["unsupported_sentences"] for e in evaluations)
        missing_sent = sum(e["missing_citation_sentences"] for e in evaluations)
        invalid_m_sent = sum(e["invalid_marker_sentences"] for e in evaluations)
        inversions = sum(e["semantic_inversions"] for e in evaluations)

        prec = (valid_cits / float(total_cits)) if total_cits > 0 else 1.0
        rec = sum(e.get("fact_recall_score", 1.0) for e in evaluations) / float(len(evaluations))
        unsupp_rate = (unsupp_sent / float(total_sent)) if total_sent > 0 else 0.0
        missing_rate = (missing_sent / float(total_sent)) if total_sent > 0 else 0.0
        invalid_m_rate = (invalid_m_sent / float(total_sent)) if total_sent > 0 else 0.0
        inv_rate = (inversions / float(total_sent)) if total_sent > 0 else 0.0

        return CitationMetricsResult(
            citation_precision=round(prec, 4),
            citation_recall=round(rec, 4),
            unsupported_claim_rate=round(unsupp_rate, 4),
            invalid_marker_rate=round(invalid_m_rate, 4),
            missing_citation_rate=round(missing_rate, 4),
            semantic_contradiction_rate=round(inv_rate, 4),
            total_sentences=total_sent,
            total_citations=total_cits,
            valid_citations=valid_cits,
        )
