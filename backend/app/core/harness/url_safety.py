"""URL safety checks for HTTP fetch tools — SSRF mitigation."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


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


def _hostname_blocked(hostname: str) -> bool:
    host = hostname.strip().lower().rstrip(".")
    if not host:
        return True
    if host in {"localhost", "localhost.localdomain"}:
        return True
    if host.endswith(".localhost"):
        return True

    # Literal IP
    try:
        return _is_blocked_ip(ipaddress.ip_address(host))
    except ValueError:
        pass

    # Resolve DNS and reject if any A/AAAA record is private/internal
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(host, None):
            if family not in (socket.AF_INET, socket.AF_INET6):
                continue
            ip_str = sockaddr[0]
            if _is_blocked_ip(ipaddress.ip_address(ip_str)):
                return True
    except socket.gaierror:
        return True

    return False


def validate_http_url(url: str) -> str:
    """Validate URL for outbound HTTP(S) fetch. Returns normalized URL string."""
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
