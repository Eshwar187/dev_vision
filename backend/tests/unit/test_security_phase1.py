from app.core.security import (
    generate_csrf_token,
    generate_session_token,
    hash_password,
    hash_session_token,
    normalize_email,
    verify_csrf_tokens,
    verify_dummy_password,
    verify_password,
)
from app.modules.identity.schemas import UserResponse


def test_argon2id_hashing_and_verification():
    password = "CorrectHorseBatteryStaple123!"
    h1 = hash_password(password)
    h2 = hash_password(password)

    assert h1.startswith("$argon2id$")
    assert h2.startswith("$argon2id$")
    # Salting invariant: same password produces different hashes
    assert h1 != h2

    assert verify_password(password, h1) is True
    assert verify_password(password, h2) is True
    assert verify_password("WrongPassword123!", h1) is False


def test_dummy_argon2_verification():
    # Should always return False
    assert verify_dummy_password("AnyPassword") is False
    assert verify_dummy_password("WrongPassword123!") is False


def test_session_and_csrf_tokens():
    session_token = generate_session_token()
    assert session_token.startswith("dvs_")
    assert len(session_token) > 40

    token_hash = hash_session_token(session_token)
    assert len(token_hash) == 64  # SHA-256 hex string

    csrf_token = generate_csrf_token()
    assert csrf_token.startswith("dvc_")
    # Invariant: CSRF token is independent from session token
    assert csrf_token != session_token

    assert verify_csrf_tokens(csrf_token, csrf_token) is True
    assert verify_csrf_tokens(csrf_token, "wrong_token") is False
    assert verify_csrf_tokens(None, csrf_token) is False
    assert verify_csrf_tokens(csrf_token, None) is False


def test_email_normalization():
    assert normalize_email("  User@Example.COM  ") == "user@example.com"
    assert normalize_email("TEST@devvision.ai") == "test@devvision.ai"


def test_user_response_schema_never_leaks_password_hash():
    fields = UserResponse.model_fields.keys()
    assert "password_hash" not in fields
    assert "password" not in fields