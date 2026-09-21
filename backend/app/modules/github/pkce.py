"""PKCE (RFC 7636) code verifier and challenge generation helpers."""

import base64
import hashlib
import re
import secrets

# RFC 7636 unreserved characters: [A-Z] / [a-z] / [0-9] / "-" / "." / "_" / "~"
PKCE_CHARACTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"


def generate_code_verifier(length: int = 64) -> str:
    """Generate a high-entropy cryptographic code_verifier for PKCE.
    RFC 7636 requires length between 43 and 128 characters.
    """
    if length < 43 or length > 128:
        raise ValueError("PKCE code_verifier length must be between 43 and 128 characters.")
    return "".join(secrets.choice(PKCE_CHARACTERS) for _ in range(length))


def generate_code_challenge(verifier: str) -> str:
    """Generate a BASE64URL-encoded SHA-256 code_challenge from a code_verifier (S256 method).
    Trailing padding characters ('=') are omitted per RFC 7636 Section 4.2.
    """
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def verify_code_challenge(verifier: str, challenge: str) -> bool:
    """Verify that a code_verifier hashes to the expected code_challenge."""
    calculated = generate_code_challenge(verifier)
    return secrets.compare_digest(calculated, challenge)
