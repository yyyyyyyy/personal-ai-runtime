"""Tests for GovernanceContextFragment — FACT-36 dormant provider activation."""

import pytest

from app.context_runtime import RuntimeContext
from app.core.runtime import read_ports
from app.core.runtime.kernel import Kernel
from app.fragments.universal.governance import GovernanceContextFragment
from app.store.database import Database


@pytest.mark.asyncio
async def test_governance_fragment_empty_when_no_state(monkeypatch):
    """With no approvals the chat-stage fragment stays empty (tools suppressed)."""
    monkeypatch.setattr(read_ports, "query_pending_approvals", lambda **kw: [])
    monkeypatch.setattr(read_ports, "query_pending_approval_count", lambda: 0)
    monkeypatch.setattr(read_ports, "query_recent_tool_names", lambda **kw: ["read_file"])
    frag = GovernanceContextFragment()
    result = await frag.collect(RuntimeContext(user_message="hello", stage="chat"))
    assert result.content == ""


@pytest.mark.asyncio
async def test_governance_fragment_shows_pending_approval_actions(monkeypatch):
    """Pending approvals list actionable capability names."""
    monkeypatch.setattr(
        read_ports,
        "query_pending_approvals",
        lambda **kw: [
            {"action": "write_file"},
            {"action": "shell_exec"},
        ],
    )
    monkeypatch.setattr(read_ports, "query_pending_approval_count", lambda: 2)
    monkeypatch.setattr(read_ports, "query_recent_tool_names", lambda **kw: [])
    frag = GovernanceContextFragment()
    result = await frag.collect(RuntimeContext(user_message="hello", stage="chat"))
    assert "待审批: write_file, shell_exec（共 2 项）" in result.content


@pytest.mark.asyncio
async def test_governance_fragment_tools_only_on_post_tool(monkeypatch):
    """Recent tools appear in post_tool even without pending approvals."""
    monkeypatch.setattr(read_ports, "query_pending_approvals", lambda **kw: [])
    monkeypatch.setattr(read_ports, "query_pending_approval_count", lambda: 0)
    monkeypatch.setattr(
        read_ports,
        "query_recent_tool_names",
        lambda **kw: ["read_file", "web_search"],
    )
    frag = GovernanceContextFragment()

    chat = await frag.collect(RuntimeContext(user_message="hello", stage="chat"))
    assert chat.content == ""

    post = await frag.collect(RuntimeContext(user_message="hello", stage="post_tool"))
    assert "read_file" in post.content
    assert "web_search" in post.content


@pytest.mark.asyncio
async def test_governance_fragment_tools_with_pending(monkeypatch):
    """Recent tools also show in chat when approvals are waiting."""
    monkeypatch.setattr(
        read_ports,
        "query_pending_approvals",
        lambda **kw: [{"action": "write_file"}],
    )
    monkeypatch.setattr(read_ports, "query_pending_approval_count", lambda: 1)
    monkeypatch.setattr(
        read_ports,
        "query_recent_tool_names",
        lambda **kw: ["write_file"],
    )
    frag = GovernanceContextFragment()
    result = await frag.collect(RuntimeContext(user_message="hello", stage="chat"))
    assert "待审批: write_file（共 1 项）" in result.content
    assert "最近工具活动: write_file" in result.content


@pytest.mark.asyncio
async def test_governance_fragment_end_to_end(tmp_path, monkeypatch):
    """Full read_ports → fragment path surfaces real pending approvals."""
    db = Database(db_path=str(tmp_path / "gov_e2e.db"))
    k = Kernel(db=db)
    k.request_approval(
        action="write_file", risk="high",
        ctx={"args": {"path": "/tmp/x"}}, actor="agent:test",
    )
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    frag = GovernanceContextFragment()
    result = await frag.collect(RuntimeContext(user_message="hello", stage="chat"))
    assert "write_file" in result.content
    assert "待审批" in result.content


def test_governance_fragment_priority_ensures_inclusion():
    """Priority >= 80 so FragmentSelector loads it in the Priority tier."""
    frag = GovernanceContextFragment()
    assert frag.priority >= 80
    assert frag.id == "core.governance"


def test_post_tool_stage_includes_governance():
    from app.core.runtime.governance.fragment_selector import POST_TOOL_FRAGMENT_IDS

    assert "core.governance" in POST_TOOL_FRAGMENT_IDS
