"""Tests for outbound URL safety checks."""

import pytest

from app.core.harness.url_safety import UnsafeUrlError, validate_http_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data",
        "http://192.168.1.1/",
        "http://10.0.0.1/",
        "file:///etc/passwd",
        "ftp://example.com/",
    ],
)
def test_blocked_urls(url: str):
    with pytest.raises(UnsafeUrlError):
        validate_http_url(url)


def test_public_https_allowed():
    assert validate_http_url("https://example.com/path").startswith("https://example.com")


def test_rejects_credentials_in_url():
    with pytest.raises(UnsafeUrlError):
        validate_http_url("http://user:pass@example.com/")
