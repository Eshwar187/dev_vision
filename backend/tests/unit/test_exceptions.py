from app.core.exceptions import (
    AppException,
    EntityNotFoundException,
    ValidationException,
    build_error_response,
)


def test_custom_exception_properties():
    exc = EntityNotFoundException("Document not found", details={"id": "123"})
    assert exc.status_code == 404
    assert exc.code == "ENTITY_NOT_FOUND"
    assert exc.details == {"id": "123"}


def test_build_error_response():
    response = build_error_response(
        code="TEST_CODE",
        message="Test message",
        status_code=400,
        request_id="req-uuid-123",
        details={"field": "missing"},
    )
    assert response.status_code == 400
    import json
    data = json.loads(response.body.decode())
    assert data["error"]["code"] == "TEST_CODE"
    assert data["error"]["message"] == "Test message"
    assert data["error"]["request_id"] == "req-uuid-123"
    assert data["error"]["details"] == {"field": "missing"}
