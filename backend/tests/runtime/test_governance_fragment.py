"""Tests for GovernanceContextFragment — FACT-36 dormant provider activation."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

import pytest

from app.context_runtime import RuntimeContext
from app.core.runtime import read_ports
from app.core.runtime.kernel import Kernel
from app.fragments.universal.governance import GovernanceContextFragment
from app.store.database import Database


@pytest.mark.asyncio
async def test_governance_fragment_empty_when_no_state(monkeypatch):
    """With no approvals/tools/stagnant goals the fragment is empty."""
    monkeypatch.setattr(read_ports, "query_pending_approval_count", lambda: 0)
    monkeypatch.setattr(read_ports, "query_recent_tool_names", lambda **kw: [])
    monkeypatch.setattr(read_ports, "query_stagnant_goal_count", lambda: 0)
    frag = GovernanceContextFragment()
    result = await frag.collect(RuntimeContext(user_message="hello"))
    assert result.content == ""


@pytest.mark.asyncio
async def test_governance_fragment_shows_pending_approvals(monkeypatch):
    """When pending approvals exist, the fragment surfaces the count."""
    monkeypatch.setattr(read_ports, "query_pending_approval_count", lambda: 2)
    monkeypatch.setattr(read_ports, "query_recent_tool_names", lambda **kw: [])
    monkeypatch.setattr(read_ports, "query_stagnant_goal_count", lambda: 0)
    frag = GovernanceContextFragment()
    result = await frag.collect(RuntimeContext(user_message="hello"))
    assert "待审批操作: 2 项" in result.content


@pytest.mark.asyncio
async def test_governance_fragment_shows_recent_tools(monkeypatch):
    """When tool events exist, the fragment lists recent tool names."""
    monkeypatch.setattr(read_ports, "query_pending_approval_count", lambda: 0)
    monkeypatch.setattr(read_ports, "query_recent_tool_names", lambda **kw: ["read_file", "web_search"])
    monkeypatch.setattr(read_ports, "query_stagnant_goal_count", lambda: 0)
    frag = GovernanceContextFragment()
    result = await frag.collect(RuntimeContext(user_message="hello"))
    assert "read_file" in result.content
    assert "web_search" in result.content


@pytest.mark.asyncio
async def test_governance_fragment_end_to_end(tmp_path, monkeypatch):
    """Full read_ports → fragment path surfaces real pending approvals."""
    db = Database(db_path=str(tmp_path / "gov_e2e.db"))
    k = Kernel(db=db)
    k.request_approval(
        action="write_file", risk="high",
        ctx={"args": {"path": "/tmp/x"}}, actor="agent:test",
    )
    # Point read_ports' kernel reference at the isolated instance.
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    frag = GovernanceContextFragment()
    result = await frag.collect(RuntimeContext(user_message="hello"))
    assert "待审批操作: 1 项" in result.content


def test_governance_fragment_priority_ensures_inclusion():
    """Priority >= 80 so FragmentSelector loads it in the Priority tier."""
    frag = GovernanceContextFragment()
    assert frag.priority >= 80
    assert frag.id == "core.governance"
