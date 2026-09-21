"""Unit tests for PKCE (S256) and HMAC-signed OAuth state management."""

import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationException
from app.modules.github.pkce import (
    generate_code_challenge,
    generate_code_verifier,
    verify_code_challenge,
)
from app.modules.github.state import (
    GitHubStateManager,
    _sign_state_payload,
    _verify_state_signature,
)


def test_pkce_verifier_and_challenge():
    """Verify PKCE verifier generation meets RFC 7636 requirements and S256 challenge computes accurately."""
    verifier = generate_code_verifier(64)
    assert len(verifier) == 64
    assert verifier.isalnum() or all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~" for c in verifier)

    challenge = generate_code_challenge(verifier)
    assert len(challenge) > 0
    assert "=" not in challenge  # Trailing padding stripped

    # Test matching
    assert verify_code_challenge(verifier, challenge) is True
    # Test mismatch
    assert verify_code_challenge(verifier + "tamper", challenge) is False


def test_hmac_state_signature_and_tampering():
    """Verify HMAC signature generation and constant-time tamper detection."""
    secret = "test_secret_key_32_characters_long_minimum"
    payload = "ws_id:user_id:nonce:1234567890"

    signature = _sign_state_payload(payload, secret)
    assert _verify_state_signature(payload, signature, secret) is True

    # Tampered payload
    tampered_payload = "ws_id:user_id:tampered_nonce:1234567890"
    assert _verify_state_signature(tampered_payload, signature, secret) is False

    # Tampered signature
    assert _verify_state_signature(payload, signature[:-1] + "x", secret) is False


@pytest.mark.asyncio
async def test_state_manager_create_and_verify(db_session: AsyncSession):
    """Verify state manager creates bound state and verifies single-use."""
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()

    signed_state, challenge, verifier = await GitHubStateManager.create_state(
        session=db_session,
        workspace_id=ws_id,
        user_id=user_id,
    )

    assert signed_state.count(":") == 4
    assert len(challenge) > 0
    assert len(verifier) == 64

    # Successful verification
    record = await GitHubStateManager.verify_and_consume_state(
        session=db_session,
        signed_state=signed_state,
        expected_workspace_id=ws_id,
        expected_user_id=user_id,
    )
    assert record.workspace_id == ws_id
    assert record.user_id == user_id
    assert record.code_verifier == verifier
    assert record.used_at is not None

    # Replay attack: state cannot be consumed twice
    with pytest.raises(ValidationException, match="already been used"):
        await GitHubStateManager.verify_and_consume_state(
            session=db_session,
            signed_state=signed_state,
            expected_workspace_id=ws_id,
            expected_user_id=user_id,
        )


@pytest.mark.asyncio
async def test_state_manager_user_mismatch(db_session: AsyncSession):
    """Verify state verification rejects session user mismatch."""
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    attacker_user_id = uuid.uuid4()

    signed_state, _, _ = await GitHubStateManager.create_state(
        session=db_session,
        workspace_id=ws_id,
        user_id=user_id,
    )

    with pytest.raises(ValidationException, match="does not match authenticated user"):
        await GitHubStateManager.verify_and_consume_state(
            session=db_session,
            signed_state=signed_state,
            expected_user_id=attacker_user_id,
        )


@pytest.mark.asyncio
async def test_state_manager_expired_state(db_session: AsyncSession):
    """Verify state verification rejects expired states."""
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    nonce = "test_nonce_123"
    expired_ts = int((datetime.now(timezone.utc) - timedelta(minutes=15)).timestamp())

    payload_str = f"{ws_id}:{user_id}:{nonce}:{expired_ts}"
    from app.core.config import get_settings
    sig = _sign_state_payload(payload_str, get_settings().SECRET_KEY)
    expired_signed_state = f"{payload_str}:{sig}"

    with pytest.raises(ValidationException, match="expired"):
        await GitHubStateManager.verify_and_consume_state(
            session=db_session,
            signed_state=expired_signed_state,
        )
