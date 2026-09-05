import hashlib
import hmac
import secrets
from typing import Optional
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from app.core.logging import get_logger

logger = get_logger("security")

# Argon2id password hasher with RFC 9106 recommended parameters
password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
)

# Static precomputed Argon2id hash for login anti-enumeration timing defense.
# Matches the exact work factor of real password verification.
DUMMY_ARGON2ID_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$4fH6fPqI3gJ7fK1m9xL4wQ$Zk3Xp9wYbQ4R1vNcM7sF2g8H5jK6lP0oI9uY3tE1rA8"
)


def normalize_email(email: str) -> str:
    """Normalizes email to lowercase and strips outer whitespace."""
    return email.strip().lower()


def hash_password(password: str) -> str:
    """Hashes a plaintext password using Argon2id with unique per-password salt."""
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against an Argon2id hash string."""
    try:
        return password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError):
        return False
    except Exception as exc:
        logger.error("Unexpected error verifying password hash", error=str(exc))
        return False


def verify_dummy_password(plain_password: str) -> bool:
    """
    Executes an Argon2id verification against a static dummy hash.
    Ensures non-existent users incur the identical computational delay
    (~50-100ms) as existing users to prevent timing-based enumeration.
    """
    try:
        password_hasher.verify(DUMMY_ARGON2ID_HASH, plain_password)
        return False
    except (VerifyMismatchError, VerificationError):
        return False
    except Exception:
        return False


def generate_session_token() -> str:
    """Generates a cryptographically secure random session token with 256 bits of entropy."""
    # 32 random bytes = 256 bits of entropy
    return f"dvs_{secrets.token_urlsafe(32)}"


def hash_session_token(token: str) -> str:
    """Computes SHA-256 hex digest of a session token for secure database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    """
    Generates an independent cryptographically secure CSRF token.
    Must not equal or derive from the session token.
    """
    return f"dvc_{secrets.token_urlsafe(32)}"


def verify_csrf_tokens(header_token: Optional[str], cookie_token: Optional[str]) -> bool:
    """Validates CSRF header and cookie tokens using constant-time string comparison."""
    if not header_token or not cookie_token:
        return False
    return hmac.compare_digest(header_token, cookie_token)