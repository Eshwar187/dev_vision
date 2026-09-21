"""Unit tests for GitHub tarball redirect validation and SSRF defenses."""

import socket
import pytest
from unittest.mock import patch

from app.core.exceptions import ValidationException
from app.modules.github.client import is_safe_ip, validate_redirect_url


def test_safe_ip_detection():
    """Verify that private, loopback, link-local, and cloud metadata IPs are rejected."""
    # Forbidden / Restricted IPs
    assert is_safe_ip("127.0.0.1") is False  # Loopback
    assert is_safe_ip("::1") is False  # IPv6 Loopback
    assert is_safe_ip("10.0.0.5") is False  # RFC 1918 Class A
    assert is_safe_ip("172.16.50.1") is False  # RFC 1918 Class B
    assert is_safe_ip("192.168.1.1") is False  # RFC 1918 Class C
    assert is_safe_ip("169.254.169.254") is False  # AWS / Cloud Metadata
    assert is_safe_ip("169.254.1.1") is False  # Link-local
    assert is_safe_ip("224.0.0.1") is False  # Multicast
    assert is_safe_ip("invalid_ip") is False

    # Safe Public IPs
    assert is_safe_ip("140.82.121.4") is True  # GitHub IP
    assert is_safe_ip("8.8.8.8") is True  # Public DNS
    assert is_safe_ip("1.1.1.1") is True  # Cloudflare DNS


def test_redirect_scheme_validation():
    """Verify that non-HTTPS redirect URLs are strictly rejected."""
    with pytest.raises(ValidationException, match="Insecure redirect scheme rejected"):
        validate_redirect_url("http://codeload.github.com/owner/repo/legacy.tar.gz")


def test_redirect_host_allowlist():
    """Verify that redirects to unapproved hosts (or wildcards) are strictly rejected."""
    with pytest.raises(ValidationException, match="Redirect to unapproved archive host rejected"):
        validate_redirect_url("https://malicious-site.com/archive.tar.gz")

    with pytest.raises(ValidationException, match="Redirect to unapproved archive host rejected"):
        validate_redirect_url("https://raw.githubusercontent.com/owner/repo/master/archive.tar.gz")

    with pytest.raises(ValidationException, match="Redirect to unapproved archive host rejected"):
        validate_redirect_url("https://github.com/owner/repo/archive.tar.gz")


def test_redirect_approved_host_with_safe_ip():
    """Verify that codeload.github.com resolving to a public IP succeeds."""
    mock_addr = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("140.82.121.9", 443))]
    with patch("socket.getaddrinfo", return_value=mock_addr):
        # Should execute cleanly without raising
        validate_redirect_url("https://codeload.github.com/owner/repo/legacy.tar.gz/sha")


def test_redirect_dns_rebinding_to_private_ip_rejected():
    """Verify that DNS resolving to an internal or metadata IP triggers an SSRF rejection."""
    # DNS returns AWS metadata IP for the hostname
    mock_addr = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))]
    with patch("socket.getaddrinfo", return_value=mock_addr):
        with pytest.raises(ValidationException, match="restricted network address"):
            validate_redirect_url("https://codeload.github.com/owner/repo/legacy.tar.gz/sha")

    # DNS returns RFC 1918 address
    mock_addr_private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))]
    with patch("socket.getaddrinfo", return_value=mock_addr_private):
        with pytest.raises(ValidationException, match="restricted network address"):
            validate_redirect_url("https://codeload.github.com/owner/repo/legacy.tar.gz/sha")
