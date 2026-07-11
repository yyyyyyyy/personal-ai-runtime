"""T2 acceptance test: Capability invocation with approval gating through Kernel."""

import json
import os
from pathlib import Path

os.environ.setdefault("LLM_API_KEY", "test-key")

import pytest

from app.core.harness.mcp_hub import mcp_hub
from app.core.runtime.kernel import Kernel
from app.store.database import Database

POLICY_PATH = Path(__file__).resolve().parents[2] / "capability_policy.json"

# Core builtin tools — always registered by MCPHub and therefore always
# required to appear in capability_policy.json.
BUILTIN_TOOLS = {
    "get_current_time",
    "read_file",
    "write_file",
    "apply_patch",
    "list_directory",
    "search_files",
    "web_search",
    "fetch_url",
    "list_calendar_events",
    "add_calendar_event",
    "get_upcoming_events",
    "check_inbox",
    "read_inbox_email",
    "send_email",
    "open_web_page",
    "search_and_extract",
    "shell_exec",
    "git_status",
    "git_log",
    "git_diff",
    "telegram_send",
    "telegram_updates",
    "create_goal",
    "update_goal_progress",
    "complete_goal",
    "list_active_goals",
}
# Advanced (opt-in) tools — registered only when BUILTIN_TOOL_CATEGORIES
# explicitly enables them. They remain in capability_policy.json so the
# governance decision is defined before the tool is ever loaded.
ADVANCED_TOOLS = {
    "get_clipboard",
    "ocr_image",
    "computer_screenshot",
    "computer_click",
    "computer_type",
    "computer_move",
    "computer_scroll",
    "computer_key",
    "computer_screen_size",
    "voice_tts",
    "voice_stt",
}


def test_capability_policy_covers_all_registered_tools():
    """Contract: every builtin mcp_hub tool must appear in capability_policy.json.

    Core tools must be registered by default. Advanced tools (computer_use,
    voice, clipboard_ocr) are opt-in but still must have a policy entry so the
    governance decision is defined before the tool is loaded.
    """
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    registered = {t["function"]["name"] for t in mcp_hub.get_tool_defs_for_llm()}
    all_known = BUILTIN_TOOLS | ADVANCED_TOOLS
    covered = (
        set(policy["auto_allow"])
        | set(policy["needs_user"])
        | set(policy.get("forbidden", []))
    )
    missing = all_known - covered
    extra = covered - all_known
    overlap = set(policy["auto_allow"]) & set(policy["needs_user"])
    # Core tools must all be registered with the default (lean) configuration.
    assert BUILTIN_TOOLS <= registered, f"Missing core builtin tools: {BUILTIN_TOOLS - registered}"
    # Every known tool (core + advanced) must have a policy decision.
    assert not missing, f"Builtin tools missing from capability_policy: {missing}"
    assert not extra, f"Unknown tools in capability_policy: {extra}"
    assert not overlap, f"Tools in both auto_allow and needs_user: {overlap}"
    assert len(BUILTIN_TOOLS) == 26


def make_kernel(tmp_path):
    db = Database(db_path=str(tmp_path / "t2.db"))
    return Kernel(db=db), db


@pytest.mark.asyncio
class TestCapabilityApproval:
    async def test_low_risk_auto_allow(self, tmp_path):
        k, _ = make_kernel(tmp_path)
        result = await k.invoke_capability(
            "get_current_time", {}, actor="test", correlation_id="corr1",
        )
        assert result["status"] == "success"
        # Verify the event trail
        events = k.read_events(correlation_id="corr1")
        types = [e.type for e in events]
        assert "ApprovalRequested" in types
        assert "ApprovalGranted" in types
        assert "CapabilityInvoked" in types

    async def test_high_risk_needs_user(self, tmp_path):
        k, _ = make_kernel(tmp_path)
        result = await k.invoke_capability(
            "write_file", {"path": "/tmp/x", "content": "hello"}, actor="test", correlation_id="corr2",
        )
        assert result["status"] == "pending"
        assert "approval_id" in result
        events = k.read_events(correlation_id="corr2")
        types = [e.type for e in events]
        assert "ApprovalRequested" in types
        assert "CapabilityDenied" in types
        # Ensure it was the deferred variant (not a hard deny).
        deferred_evt = next(e for e in events if e.type == "CapabilityDenied")
        assert deferred_evt.payload.get("reason") == "deferred"
        assert "ApprovalGranted" not in types
        assert "CapabilityInvoked" not in types

    async def test_full_trace_with_correlation_id(self, tmp_path):
        k, _ = make_kernel(tmp_path)
        cid = "trace_full"
        await k.invoke_capability("get_current_time", {}, actor="test", correlation_id=cid)
        await k.invoke_capability("list_directory", {"path": "."}, actor="test", correlation_id=cid)

        trace = k.read_events(correlation_id=cid)
        assert len(trace) >= 4  # at least 2x Approval + 2x Capability for the two calls
        trace_types = [e.type for e in trace]
        assert trace_types.count("CapabilityInvoked") == 2
        assert trace_types.count("ApprovalGranted") == 2

    async def test_approval_projection(self, tmp_path):
        k, _ = make_kernel(tmp_path)
        r = await k.invoke_capability("get_current_time", {}, actor="user", correlation_id="c_apr")
        aid = r.get("approval_id") or (
            k.read_events(correlation_id="c_apr")[1].aggregate_id
        )

        with k._db.get_db() as conn:
            row = conn.execute("SELECT * FROM approvals WHERE id = ?", (aid,)).fetchone()
        assert row is not None
        assert row["status"] == "approved"
        assert row["action"] == "get_current_time"

    async def test_pre_approved_requires_approval_id(self, tmp_path):
        k, _ = make_kernel(tmp_path)
        result = await k.invoke_capability(
            "write_file",
            {"path": "/tmp/x", "content": "hi"},
            actor="user",
            pre_approved=True,
        )
        assert result["status"] == "error"
        assert "approval_id" in result["error"]

    async def test_pre_approved_rejects_mismatched_args(self, tmp_path):
        k, _ = make_kernel(tmp_path)
        pending = await k.invoke_capability(
            "write_file",
            {"path": "/tmp/x", "content": "hi"},
            actor="user",
            correlation_id="mismatch",
        )
        result = await k.invoke_capability(
            "write_file",
            {"path": "/tmp/x", "content": "evil"},
            actor="user",
            pre_approved=True,
            approval_id=pending["approval_id"],
        )
        assert result["status"] == "error"
        assert "params" in result["error"]

    async def test_pre_approved_cannot_replay(self, tmp_path):
        k, _ = make_kernel(tmp_path)
        pending = await k.invoke_capability(
            "write_file",
            {"path": "/tmp/x", "content": "hi"},
            actor="user",
            correlation_id="replay",
        )
        approval_id = pending["approval_id"]
        args = {"path": "/tmp/x", "content": "hi"}

        first = await k.invoke_capability(
            "write_file",
            args,
            actor="user",
            pre_approved=True,
            approval_id=approval_id,
        )
        assert first["status"] == "success"

        second = await k.invoke_capability(
            "write_file",
            args,
            actor="user",
            pre_approved=True,
            approval_id=approval_id,
        )
        assert second["status"] == "error"
        assert "pending" in second["error"]

    async def test_pre_approved_skips_new_approval(self, tmp_path):
        k, _ = make_kernel(tmp_path)
        pending = await k.invoke_capability(
            "write_file", {"path": "/tmp/x", "content": "hi"}, actor="user", correlation_id="pre",
        )
        assert pending["status"] == "pending"
        approval_id = pending["approval_id"]

        result = await k.invoke_capability(
            "write_file",
            {"path": "/tmp/x", "content": "hi"},
            actor="user",
            correlation_id="pre_exec",
            pre_approved=True,
            approval_id=approval_id,
        )
        assert result["status"] == "success"
        events = k.read_events(correlation_id="pre_exec")
        types = [e.type for e in events]
        assert "ApprovalRequested" not in types
        assert "CapabilityInvoked" in types

    async def test_rebuild_approval_projection(self, tmp_path):
        k, _ = make_kernel(tmp_path)
        await k.invoke_capability("get_current_time", {}, actor="user", correlation_id="c_reb")
        await k.invoke_capability("write_file", {"path": "/x", "content": "y"}, actor="user", correlation_id="c_reb2")

        before = []
        with k._db.get_db() as conn:
            before = [dict(r) for r in conn.execute("SELECT * FROM approvals ORDER BY created_at").fetchall()]

        k.rebuild("approval")

        after = []
        with k._db.get_db() as conn:
            after = [dict(r) for r in conn.execute("SELECT * FROM approvals ORDER BY created_at").fetchall()]

        assert before == after, "approval projection must be byte-identical after rebuild"
        assert len(after) == 2
