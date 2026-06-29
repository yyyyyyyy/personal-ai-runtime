"""URL safety checks for HTTP fetch tools — SSRF mitigation.

Two layers of defense:

1. ``validate_http_url`` — pre-flight URL validation (scheme, hostname, DNS).
   Used by ``shell.py`` for curl/wget and as the first gate for fetch tools.

2. ``create_ssrf_safe_async_client`` — DNS-pinned transport that pins every
   outbound connection to an IP resolved and validated *at request time*,
   eliminating the TOCTOU/DNS-rebinding window between hook validation and
   httpx's own resolution. Without pinning, a malicious authoritative resolver
   with TTL=0 can return a public IP to the validation hook and then resolve to
   127.0.0.1 / 169.254.169.254 when httpx actually opens the socket.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx


class UnsafeUrlError(ValueError):
    """Raised when a URL targets a disallowed host or scheme."""


def _is_blocked_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _resolve_and_check(hostname: str) -> list[str]:
    """Resolve ``hostname`` and return the list of public IP strings.

    Raises UnsafeUrlError if the host is blocked or cannot be resolved.
    All returned addresses are individually validated, so a hostname with a mix
    of public and private records is rejected wholesale.
    """
    host = hostname.strip().lower().rstrip(".")
    if not host:
        raise UnsafeUrlError("Empty hostname")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise UnsafeUrlError(f"Blocked hostname: {hostname}")

    # Literal IP — validate directly, no DNS lookup needed.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if _is_blocked_ip(ip):
            raise UnsafeUrlError(f"Blocked IP literal: {host}")
        return [host]

    ips: list[str] = []
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(host, None):
            if family not in (socket.AF_INET, socket.AF_INET6):
                continue
            ip_str = sockaddr[0]
            if _is_blocked_ip(ipaddress.ip_address(ip_str)):
                raise UnsafeUrlError(
                    f"Hostname {hostname!r} resolves to blocked address {ip_str}"
                )
            if ip_str not in ips:
                ips.append(ip_str)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Could not resolve {hostname!r}: {exc}") from exc

    if not ips:
        raise UnsafeUrlError(f"Hostname {hostname!r} has no usable records")
    return ips


def _hostname_blocked(hostname: str) -> bool:
    """Backward-compatible boolean wrapper for pre-flight checks."""
    try:
        _resolve_and_check(hostname)
    except UnsafeUrlError:
        return True
    return False


def validate_http_url(url: str) -> str:
    """Validate URL for outbound HTTP(S) fetch. Returns normalized URL string.

    Performs scheme/credential checks and a *pre-flight* DNS resolution. This is
    the right gate for tools that do not use httpx (curl/wget in ``shell.py``);
    httpx callers additionally use ``create_ssrf_safe_async_client`` to pin the
    connection to the resolved IP at socket time.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError(f"Unsupported URL scheme: {parsed.scheme or '(none)'}")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeUrlError("URL missing hostname")

    if _hostname_blocked(hostname):
        raise UnsafeUrlError(f"Blocked hostname: {hostname}")

    # Reject credentials in URL
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URLs with embedded credentials are not allowed")

    return parsed.geturl()


def _pin_url_to_ip(url: str, ip: str) -> str:
    """Rewrite the host of ``url`` to the literal ``ip``, preserving port.

    IPv6 literals are wrapped in brackets per RFC 3986 (``[2001:db8::1]``) so
    the colon in the address is not mistaken for a port separator. The Host
    header (used for TLS SNI and virtual hosting) is restored separately by
    ``_restore_host_header`` so the origin server still sees the original name.
    """
    parsed = urlparse(url)
    # Detect IPv6 literal (colon present, not already bracketed).
    if ":" in ip and not ip.startswith("["):
        host_part = f"[{ip}]"
    else:
        host_part = ip
    if parsed.port:
        netloc = f"{host_part}:{parsed.port}"
    else:
        netloc = host_part
    return parsed._replace(netloc=netloc).geturl()


def _restore_host_header(request: httpx.Request, original_host: str) -> None:
    """Restore Host to the original hostname so TLS SNI / vhost routing works."""
    request.headers["Host"] = original_host


class SSRFSafeTransport(httpx.AsyncBaseTransport):
    """Async transport that pins every request to a validated, resolved IP.

    Per-request resolution closes the DNS-rebinding window: the IP validated at
    request time is the same IP the socket connects to. Each resolved address
    is checked against ``_is_blocked_ip`` before any connection is attempted.
    """

    def __init__(self, **kwargs: Any) -> None:
        # follow_redirects is owned by httpx.AsyncClient, not the transport.
        kwargs.pop("follow_redirects", None)
        self._inner = httpx.AsyncHTTPTransport(**kwargs)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise UnsafeUrlError(f"Unsupported URL scheme: {parsed.scheme or '(none)'}")
        if parsed.username or parsed.password:
            raise UnsafeUrlError("URLs with embedded credentials are not allowed")

        hostname = parsed.hostname
        if not hostname:
            raise UnsafeUrlError("URL missing hostname")

        ips = _resolve_and_check(hostname)
        pinned_ip = ips[0]
        # Host header should preserve the original port so HTTP vhost routing
        # on non-standard ports works correctly. For SNI only the name matters,
        # but including the port is harmless for TLS.
        original_host = f"{hostname}:{parsed.port}" if parsed.port else hostname

        # Materialize the request body before rewriting the URL. Reusing
        # ``request.stream`` directly fails for POST/PUT/PATCH because the
        # stream is a single-consumer SyncByteStream that cannot be replayed
        # into a new Request. Reading it to bytes here is safe — the body
        # has not been consumed yet at transport entry time.
        body_bytes = await request.aread()

        pinned_url = _pin_url_to_ip(url, pinned_ip)
        pinned_request = request.__class__(
            method=request.method,
            url=pinned_url,
            headers=request.headers,
            params=request.url.params,
            content=body_bytes,
        )
        _restore_host_header(pinned_request, original_host)
        return await self._inner.handle_async_request(pinned_request)


async def _validate_redirect_target(response: httpx.Response) -> None:
    """Validate redirect destinations through the same host checks.

    The pinned transport already enforces pinning for the redirect's actual
    request; this hook adds an explicit, logged rejection of obviously-internal
    redirect targets (defense in depth).
    """
    if response.is_redirect and response.next_request is not None:
        validate_http_url(str(response.next_request.url))


def create_ssrf_safe_async_client(**kwargs: Any) -> httpx.AsyncClient:
    """Build an httpx client with DNS-pinned outbound connections.

    The transport pins each request to an IP resolved and validated at request
    time, so a DNS resolver that flips records between validation and connection
    (DNS rebinding) cannot redirect the socket to a private/internal address.
    A response hook still validates redirect targets for defense in depth.
    """
    follow_redirects = kwargs.pop("follow_redirects", True)
    transport = SSRFSafeTransport()
    hooks = dict(kwargs.pop("event_hooks", {}))
    response_hooks = [_validate_redirect_target, *hooks.get("response", [])]
    return httpx.AsyncClient(
        transport=transport,
        follow_redirects=follow_redirects,
        event_hooks={"response": response_hooks} if response_hooks else None,
        **kwargs,
    )
