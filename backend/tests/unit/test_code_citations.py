from app.modules.codebase.citations import CodeCitationValidator


def test_valid_citation_marker_preserved():
    answer = "The authentication service verifies tokens [SNIPPET_1] and caches user claims [SNIPPET_2]."
    res = CodeCitationValidator.validate_and_filter(answer, retrieved_chunk_count=2)
    assert res.is_grounded is True
    assert res.valid_citations == [1, 2]
    assert len(res.stripped_markers) == 0
    assert "[SNIPPET_1]" in res.sanitized_answer
    assert "[SNIPPET_2]" in res.sanitized_answer


def test_invalid_marker_stripped():
    answer = "This claims something completely ungrounded [SNIPPET_99] and also [SNIPPET_5]."
    res = CodeCitationValidator.validate_and_filter(answer, retrieved_chunk_count=2)
    assert 99 in res.stripped_markers or "[SNIPPET_99]" in res.stripped_markers
    assert "[SNIPPET_99]" not in res.sanitized_answer
    assert "[SNIPPET_5]" not in res.sanitized_answer


def test_refusal_phrase_detected():
    answer = "I cannot answer based on the indexed codebase."
    res = CodeCitationValidator.validate_and_filter(answer, retrieved_chunk_count=3)
    assert res.is_refusal is True
    assert res.is_grounded is True