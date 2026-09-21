"""HMAC-signed OAuth state generation, verification, and single-use enforcement."""

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ValidationException
from app.modules.github.models import GitHubOAuthState
from app.modules.github.pkce import generate_code_challenge, generate_code_verifier

settings = get_settings()


def _sign_state_payload(payload_str: str, secret_key: str) -> str:
    """Generate HMAC-SHA256 signature for a state payload string."""
    sig = hmac.new(
        secret_key.encode("utf-8"),
        payload_str.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")


def _verify_state_signature(payload_str: str, signature: str, secret_key: str) -> bool:
    """Constant-time comparison of state HMAC-SHA256 signature."""
    expected = _sign_state_payload(payload_str, secret_key)
    return secrets.compare_digest(expected, signature)


class GitHubStateManager:
    @staticmethod
    async def create_state(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Tuple[str, str, str]:
        """Generate PKCE verifier, challenge, and an HMAC-signed single-use state token.
        Persists state record in github_oauth_states.
        Returns: (signed_state, code_challenge, code_verifier)
        """
        nonce = secrets.token_hex(32)
        code_verifier = generate_code_verifier(64)
        code_challenge = generate_code_challenge(code_verifier)

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=settings.GITHUB_OAUTH_STATE_EXPIRE_SECONDS)
        expires_at_ts = int(expires_at.timestamp())

        # Payload: workspace_id:user_id:nonce:expires_at_ts
        payload_str = f"{workspace_id}:{user_id}:{nonce}:{expires_at_ts}"
        signature = _sign_state_payload(payload_str, settings.SECRET_KEY)
        signed_state = f"{payload_str}:{signature}"

        # Persist state record
        state_record = GitHubOAuthState(
            nonce=nonce,
            workspace_id=workspace_id,
            user_id=user_id,
            code_verifier=code_verifier,
            expires_at=expires_at,
            used_at=None,
        )
        session.add(state_record)
        await session.flush()

        return signed_state, code_challenge, code_verifier

    @staticmethod
    async def verify_and_consume_state(
        session: AsyncSession,
        signed_state: str,
        expected_workspace_id: Optional[uuid.UUID] = None,
        expected_user_id: Optional[uuid.UUID] = None,
    ) -> GitHubOAuthState:
        """Verify HMAC signature, expiration, user/workspace binding, and single-use constraint.
        Atomically marks state as used. Returns the verified state record with code_verifier.
        Raises ValidationException on any security violation.
        """
        parts = signed_state.split(":")
        if len(parts) != 5:
            raise ValidationException("Malformed OAuth state parameter.")

        ws_str, user_str, nonce, exp_str, signature = parts
        payload_str = f"{ws_str}:{user_str}:{nonce}:{exp_str}"

        # 1. Cryptographic HMAC signature check
        if not _verify_state_signature(payload_str, signature, settings.SECRET_KEY):
            raise ValidationException("Invalid OAuth state signature.")

        # 2. Expiry check
        try:
            exp_ts = int(exp_str)
        except ValueError:
            raise ValidationException("Invalid OAuth state expiration.")

        now_ts = int(datetime.now(timezone.utc).timestamp())
        if now_ts > exp_ts:
            raise ValidationException("OAuth state has expired. Please initiate connection again.")

        try:
            ws_id = uuid.UUID(ws_str)
            u_id = uuid.UUID(user_str)
        except ValueError:
            raise ValidationException("Invalid UUID in OAuth state.")

        if expected_workspace_id and ws_id != expected_workspace_id:
            raise ValidationException("OAuth state does not match active workspace.")
        if expected_user_id and u_id != expected_user_id:
            raise ValidationException("OAuth state does not match authenticated user session.")

        # 3. Retrieve state record with row lock to enforce atomic single-use
        stmt = (
            select(GitHubOAuthState)
            .where(GitHubOAuthState.nonce == nonce)
            .with_for_update()
        )
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()

        if not record:
            raise ValidationException("OAuth state not found or invalid.")

        if record.used_at is not None:
            raise ValidationException("OAuth state has already been used (replay detected).")

        now = datetime.now(timezone.utc)
        record_exp = record.expires_at
        if record_exp.tzinfo is None:
            record_exp = record_exp.replace(tzinfo=timezone.utc)
        if record_exp < now:
            raise ValidationException("OAuth state has expired.")

        # 4. Mark state used atomically
        record.used_at = now
        await session.flush()

        return record
