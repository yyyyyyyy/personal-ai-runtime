"""Tests for the auth bind-address check in app.main.

Previously only the wildcard binds (0.0.0.0, ::) triggered the AUTH_TOKEN
requirement; LAN IPs like 192.168.1.100 silently fell through to a warning.
``_is_localhost_bind`` closes that gap: every non-loopback bind counts as
exposed.
"""

from app.main import _is_localhost_bind


def test_loopback_ipv4_is_localhost():
    assert _is_localhost_bind("127.0.0.1") is True


def test_loopback_higher_octet_is_localhost():
    assert _is_localhost_bind("127.1.2.3") is True


def test_localhost_name_is_localhost():
    assert _is_localhost_bind("localhost") is True


def test_ipv6_loopback_is_localhost():
    assert _is_localhost_bind("::1") is True


def test_wildcard_ipv4_is_exposed():
    assert _is_localhost_bind("0.0.0.0") is False


def test_wildcard_ipv6_is_exposed():
    assert _is_localhost_bind("::") is False


def test_lan_ip_is_exposed():
    assert _is_localhost_bind("192.168.1.100") is False


def test_private_10_network_is_exposed():
    assert _is_localhost_bind("10.0.0.5") is False


def test_public_ip_is_exposed():
    assert _is_localhost_bind("8.8.8.8") is False
