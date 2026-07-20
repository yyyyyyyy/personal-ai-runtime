"""Tests for untrusted-source taint escalation."""

import json
from pathlib import Path

import pytest

from app.config import settings
from app.core.harness.mcp_hub import mcp_hub
from app.core.runtime.taint import (
    EXTERNAL_INGESTION_TOOLS,
    WRITE_CLASS_TOOLS,
    taint_registry,
)

POLICY_PATH = Path(settings.capability_policy_path)

@pytest.fixture
def kernel(isolated_kernel):
    k, _db = isolated_kernel
    return k

def test_write_class_tools_match_capability_policy():
    """Contract: taint write-class set is loaded from capability_policy needs_user."""
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    assert WRITE_CLASS_TOOLS == frozenset(policy["needs_user"])
    assert "write_file" in WRITE_CLASS_TOOLS

def test_external_ingestion_tools_loaded_from_policy():
    """Contract: external ingestion set is loaded from capability_policy."""
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    assert "external_ingestion" in policy
    assert EXTERNAL_INGESTION_TOOLS == frozenset(policy["external_ingestion"])
    assert EXTERNAL_INGESTION_TOOLS  # non-empty

def test_external_ingestion_tools_are_registered_mcp_tools():
    """Contract: external ingestion tools must exist in mcp_hub."""
    registered = {t["function"]["name"] for t in mcp_hub.get_tool_defs_for_llm()}
    unknown = EXTERNAL_INGESTION_TOOLS - registered
    assert not unknown, f"Unknown external ingestion tools: {unknown}"

def test_external_ingestion_tools_are_auto_allow_in_policy():
    """External ingestion stays low-risk until taint escalates write-class calls."""
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    auto_allow = set(policy["auto_allow"])
    assert EXTERNAL_INGESTION_TOOLS <= auto_allow

@pytest.mark.asyncio
async def test_tainted_write_forces_high_risk(kernel):
    corr = "corr-taint-write"
    taint_registry.mark(corr, source="external_ingestion", reason="check_inbox")

    result = await kernel.invoke_capability(
        name="write_file",
        args={"path": "/tmp/x", "content": "injected"},
        actor="user",
        correlation_id=corr,
        pre_approved=False,
    )

    assert result["status"] == "pending"
    assert "approval_id" in result

    taint_registry.clear(corr)

@pytest.mark.asyncio
async def test_tainted_shell_exec_forces_approval(kernel):
    corr = "corr-taint-shell"
    taint_registry.mark(corr, source="external_ingestion", reason="fetch_url")

    result = await kernel.invoke_capability(
        name="shell_exec",
        args={"command": "echo hello"},
        actor="user",
        correlation_id=corr,
        pre_approved=False,
    )

    assert result["status"] == "pending"
    assert "approval_id" in result

    taint_registry.clear(corr)

@pytest.mark.asyncio
async def test_kernel_marks_taint_after_external_ingestion(kernel, monkeypatch):
    """Taint marking lives in Kernel so all ingestion paths are covered."""
    from app.core.harness.mcp_hub import mcp_hub

    async def fake_invoke(name, args):
        return '{"content": "untrusted"}'

    monkeypatch.setattr(mcp_hub, "invoke_tool", fake_invoke)

    corr = "kernel-ingestion-taint"
    result = await kernel.invoke_capability(
        name="fetch_url",
        args={"url": "https://example.com"},
        actor="user",
        correlation_id=corr,
    )
    assert result["status"] == "success"
    assert taint_registry.is_tainted(corr)

    taint_registry.clear(corr)

@pytest.mark.asyncio
async def test_untainted_low_risk_tool_auto_allowed(kernel):
    """read_file is auto_allow and should not require approval when context is clean."""
    corr = "corr-clean"
    result = await kernel.invoke_capability(
        name="read_file",
        args={"path": "/etc/hosts"},
        actor="user",
        correlation_id=corr,
        pre_approved=False,
    )

    assert result["status"] == "success"
    taint_registry.clear(corr)
