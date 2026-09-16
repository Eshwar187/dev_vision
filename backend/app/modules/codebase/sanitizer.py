import math
import re
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

# Fatal secret filenames that MUST cause the entire file to be dropped
FATAL_SECRET_FILENAMES: Set[str] = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.staging",
    "id_rsa",
    "id_ecdsa",
    "id_ed25519",
    "id_dsa",
    "credentials.json",
    "service-account.json",
    "secrets.json",
    "secring.gpg",
}

FATAL_SECRET_EXTENSIONS: Set[str] = {
    ".pem",
    ".key",
    ".pkcs12",
    ".p12",
    ".pfx",
    ".kdbx",
}

# Regex patterns for known sensitive tokens inside source code
SECRET_PATTERNS = [
    # AWS Access Key
    (re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), "[REDACTED_AWS_KEY]"),
    # GitHub Personal Access Token
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{36,255})\b"), "[REDACTED_GITHUB_TOKEN]"),
    # Slack Token
    (re.compile(r"\b(xox[baprs]-[0-9a-zA-Z-]{10,72})\b"), "[REDACTED_SLACK_TOKEN]"),
    # Generic Private Key Block
    (re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[^-]+-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
    # Stripe Secret Key
    (re.compile(r"\b(sk_live_[0-9a-zA-Z]{24,34})\b"), "[REDACTED_STRIPE_KEY]"),
    # Generic High-Confidence Token / Secret Assignment
    (re.compile(r"""(?i)(?:api_key|secret_key|auth_token|client_secret|private_key|access_token|password)\s*[:=]\s*['"]([A-Za-z0-9_\-\.]{16,128})['"]"""), None),
]


def shannon_entropy(data: str) -> float:
    if not data:
        return 0.0
    entropy = 0.0
    for x in set(data):
        p_x = float(data.count(x)) / len(data)
        if p_x > 0:
            entropy += - p_x * math.log2(p_x)
    return entropy


@dataclass
class SanitizedFileResult:
    is_dropped: bool
    drop_reason: Optional[str]
    sanitized_text: str
    redaction_count: int


class SecretSanitizer:
    @staticmethod
    def is_fatal_secret_file(filename: str, path: str) -> bool:
        lower_fn = filename.lower()
        if lower_fn in FATAL_SECRET_FILENAMES:
            return True
        if lower_fn.startswith(".env.") or lower_fn == ".env":
            return True
        for ext in FATAL_SECRET_EXTENSIONS:
            if lower_fn.endswith(ext):
                return True
        return False

    @classmethod
    def sanitize_source(cls, filename: str, path: str, raw_bytes: bytes) -> SanitizedFileResult:
        # 1. Fatal file check
        if cls.is_fatal_secret_file(filename, path):
            return SanitizedFileResult(
                is_dropped=True,
                drop_reason="fatal_secret_file",
                sanitized_text="",
                redaction_count=0,
            )

        # 2. Decode text (strict UTF-8 with replacement for non-UTF8 chars)
        try:
            text_content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text_content = raw_bytes.decode("latin-1")
            except Exception:
                return SanitizedFileResult(
                    is_dropped=True,
                    drop_reason="undecodable_binary",
                    sanitized_text="",
                    redaction_count=0,
                )

        # Quick check for fatal private key blocks in text
        if "-----BEGIN " in text_content and "PRIVATE KEY-----" in text_content:
            return SanitizedFileResult(
                is_dropped=True,
                drop_reason="contains_private_key_block",
                sanitized_text="",
                redaction_count=0,
            )

        redaction_count = 0
        sanitized_lines = []

        # 3. Process line-by-line to strictly PRESERVE newline counts and line numbers
        for line in text_content.split("\n"):
            current_line = line
            for pattern, replacement in SECRET_PATTERNS:
                if replacement is not None:
                    # Direct regex replacement
                    matches = list(pattern.finditer(current_line))
                    if matches:
                        redaction_count += len(matches)
                        current_line = pattern.sub(replacement, current_line)
                else:
                    # Contextual assignment pattern (e.g. api_key = "...")
                    def _redact_assignment(match: re.Match) -> str:
                        nonlocal redaction_count
                        secret_val = match.group(1)
                        # Check entropy or length
                        if len(secret_val) >= 20 and shannon_entropy(secret_val) >= 3.2:
                            redaction_count += 1
                            full = match.group(0)
                            return full.replace(secret_val, "[REDACTED_SECRET]")
                        return match.group(0)

                    current_line = pattern.sub(_redact_assignment, current_line)

            sanitized_lines.append(current_line)

        final_sanitized_text = "\n".join(sanitized_lines)
        return SanitizedFileResult(
            is_dropped=False,
            drop_reason=None,
            sanitized_text=final_sanitized_text,
            redaction_count=redaction_count,
        )
