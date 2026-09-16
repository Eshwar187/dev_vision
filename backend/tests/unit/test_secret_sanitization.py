import pytest
from app.modules.codebase.sanitizer import SecretSanitizer


def test_fatal_secret_files_dropped():
    fatal_cases = [
        (".env", ".env", b"SECRET=123"),
        (".env.local", ".env.local", b"KEY=abc"),
        ("id_rsa", "keys/id_rsa", b"some-key"),
        ("credentials.json", "config/credentials.json", b"{}"),
        ("cert.pem", "certs/cert.pem", b"certificate"),
        ("private.key", "keys/private.key", b"keydata"),
    ]
    for filename, path, raw in fatal_cases:
        res = SecretSanitizer.sanitize_source(filename, path, raw)
        assert res.is_dropped is True
        assert res.sanitized_text == ""
        assert res.drop_reason == "fatal_secret_file"


def test_in_file_secrets_redacted_line_counts_preserved():
    raw_code = (
        "import os\n"
        "# AWS Access Key\n"
        "AWS_KEY = \"AKIAIOSFODNN7EXAMPLE\"\n"
        "# GitHub Token\n"
        "GH_TOKEN = \"ghp_abcdefghijklmnopqrstuvwxyz1234567890\"\n"
        "def run():\n"
        "    return True\n"
    ).encode("utf-8")

    res = SecretSanitizer.sanitize_source("client.py", "src/client.py", raw_code)
    assert res.is_dropped is False
    assert res.redaction_count >= 2
    assert "AKIAIOSFODNN7EXAMPLE" not in res.sanitized_text
    assert "[REDACTED_AWS_KEY]" in res.sanitized_text
    assert "ghp_abcdefghijklmnopqrstuvwxyz1234567890" not in res.sanitized_text
    assert "[REDACTED_GITHUB_TOKEN]" in res.sanitized_text

    # Verify line numbers are preserved exactly
    orig_lines = raw_code.decode("utf-8").split("\n")
    sanitized_lines = res.sanitized_text.split("\n")
    assert len(orig_lines) == len(sanitized_lines)
    assert sanitized_lines[5].strip() == "def run():"


def test_drop_source_with_embedded_private_key_block():
    raw_code = (
        "def get_key():\n"
        "    return '''-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n-----END RSA PRIVATE KEY-----'''\n"
    ).encode("utf-8")

    res = SecretSanitizer.sanitize_source("crypto.py", "src/crypto.py", raw_code)
    assert res.is_dropped is True
    assert res.drop_reason == "contains_private_key_block"