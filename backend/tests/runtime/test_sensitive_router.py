"""Tests for sensitive_router."""

import pytest

from app.core.runtime.capability_governance import SensitiveRouter, sensitive_router


@pytest.fixture
def router():
    return SensitiveRouter()


def test_not_sensitive_when_disabled(router, monkeypatch):
    monkeypatch.setattr("app.core.runtime.capability_governance.settings.sensitive_ops_local", False)
    assert router.is_sensitive_capability("write_file", {"path": "/secret"}) is False
    assert router.elevated_risk("write_file") == ""


def test_write_tools_sensitive_when_enabled(router, monkeypatch):
    monkeypatch.setattr("app.core.runtime.capability_governance.settings.sensitive_ops_local", True)
    assert router.is_sensitive_capability("write_file") is True
    assert router.elevated_risk("shell_exec") == "high"


def test_sensitive_patterns_in_args(router, monkeypatch):
    monkeypatch.setattr("app.core.runtime.capability_governance.settings.sensitive_ops_local", True)
    assert router.is_sensitive_capability("read_file", {"path": "/Users/me/file.txt"}) is True
    assert router.is_sensitive_capability("read_file", {"content": "api_key=abc"}) is True
    assert router.is_sensitive_capability("read_file", {"path": "/tmp/safe.txt"}) is False


def test_singleton_instance():
    assert isinstance(sensitive_router, SensitiveRouter)

def test_elevated_risk_empty_for_non_sensitive(router, monkeypatch):
    monkeypatch.setattr(
        "app.core.runtime.capability_governance.settings.sensitive_ops_local", True
    )
    assert router.elevated_risk("read_file") == ""
