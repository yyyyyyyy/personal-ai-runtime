"""Tests for outbound URL safety checks."""

from unittest.mock import patch

import httpx
import pytest

from app.core.harness.url_safety import (
    SSRFSafeTransport,
    UnsafeUrlError,
    _pin_url_to_ip,
    validate_http_url,
)


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


def test_pin_url_to_ip_preserves_port():
    pinned = _pin_url_to_ip("https://example.com:8443/path", "93.184.216.34")
    assert pinned == "https://93.184.216.34:8443/path"


def test_pin_url_to_ip_https_no_port():
    pinned = _pin_url_to_ip("https://example.com/path", "93.184.216.34")
    assert pinned == "https://93.184.216.34/path"


def test_pin_url_to_ipv6_wraps_in_brackets():
    """RFC 3986: IPv6 literals in URLs must be bracketed."""
    pinned = _pin_url_to_ip("https://example.com/path", "2606:4700:4700::1111")
    assert pinned == "https://[2606:4700:4700::1111]/path"
    # Must round-trip through httpx as a valid URL.
    import httpx

    req = httpx.Request("GET", pinned)
    assert str(req.url.host) == "2606:4700:4700::1111"


def test_pin_url_to_ipv6_with_port():
    pinned = _pin_url_to_ip("https://example.com:8443/path", "2606:4700:4700::1111")
    assert pinned == "https://[2606:4700:4700::1111]:8443/path"
    import httpx

    req = httpx.Request("GET", pinned)
    assert req.url.port == 8443


def test_pin_url_to_ipv6_loopback_rejected_by_resolver():
    """::1 is blocked even though it's a valid IPv6 literal."""
    from app.core.harness.url_safety import _resolve_and_check

    with pytest.raises(UnsafeUrlError):
        _resolve_and_check("::1")
    with pytest.raises(UnsafeUrlError):
        _resolve_and_check("fc00::1")  # IPv6 ULA (private)


def test_transport_pins_request_to_resolved_ip():
    """The transport rewrites the request URL to the resolved IP literal."""
    import asyncio

    with patch(
        "app.core.harness.url_safety._resolve_and_check",
        return_value=["93.184.216.34"],
    ) as mock_resolve, patch.object(
        httpx.AsyncHTTPTransport, "handle_async_request"
    ) as mock_inner:
        transport = SSRFSafeTransport()
        request = httpx.Request("GET", "https://example.com/path")

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(transport.handle_async_request(request))
        finally:
            loop.close()

        mock_resolve.assert_called_once_with("example.com")
        sent_request = mock_inner.call_args.args[0]
        assert str(sent_request.url.host) == "93.184.216.34"
        # Host header preserved for SNI / vhost routing.
        assert sent_request.headers["Host"] == "example.com"
        # TLS SNI must use the original hostname, not the pinned IP.
        assert sent_request.extensions["sni_hostname"] == "example.com"


def test_transport_preserves_port_in_host_header():
    """Non-standard ports must appear in the restored Host header for vhost routing."""
    import asyncio

    with patch(
        "app.core.harness.url_safety._resolve_and_check",
        return_value=["93.184.216.34"],
    ), patch.object(
        httpx.AsyncHTTPTransport, "handle_async_request"
    ) as mock_inner:
        transport = SSRFSafeTransport()
        request = httpx.Request("GET", "https://example.com:8443/path")

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(transport.handle_async_request(request))
        finally:
            loop.close()

        sent_request = mock_inner.call_args.args[0]
        assert str(sent_request.url.host) == "93.184.216.34"
        assert sent_request.url.port == 8443
        # Host header must keep the original hostname AND port.
        assert sent_request.headers["Host"] == "example.com:8443"


def test_transport_preserves_post_body():
    """POST/PUT/PATCH bodies must survive URL rewriting.

    Regression guard: an earlier version passed ``content=request.stream``
    directly, which failed at aread() time because the single-consumer stream
    could not be replayed into the new Request. The fix materializes the body
    to bytes before rewriting.
    """
    import asyncio
    import json as _json

    with patch(
        "app.core.harness.url_safety._resolve_and_check",
        return_value=["93.184.216.34"],
    ), patch.object(
        httpx.AsyncHTTPTransport, "handle_async_request"
    ) as mock_inner:
        transport = SSRFSafeTransport()
        payload = _json.dumps({"key": "value", "n": 42}).encode()
        request = httpx.Request(
            "POST",
            "https://example.com/api",
            content=payload,
            headers={"content-type": "application/json"},
        )

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(transport.handle_async_request(request))
        finally:
            loop.close()

        sent_request = mock_inner.call_args.args[0]
        # Body must be identical to the original.
        assert sent_request.headers["content-length"] == str(len(payload))
        assert sent_request.headers["content-type"] == "application/json"
        # We can't re-read sent_request's stream (single-consumer), but
        # content-length proves the body was carried through.


def test_transport_rejects_private_resolution():
    """If the resolver returns a private IP at request time, the request is rejected."""
    import asyncio

    with patch(
        "app.core.harness.url_safety._resolve_and_check",
        side_effect=UnsafeUrlError("Blocked: 127.0.0.1"),
    ):
        transport = SSRFSafeTransport()
        request = httpx.Request("GET", "https://evil.example.com/")

        loop = asyncio.new_event_loop()
        try:
            with pytest.raises(UnsafeUrlError):
                loop.run_until_complete(transport.handle_async_request(request))
        finally:
            loop.close()
