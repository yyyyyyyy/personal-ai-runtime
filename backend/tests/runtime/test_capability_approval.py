"""T2 acceptance test: Capability invocation with approval gating through Kernel."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

import pytest

from app.core.runtime.kernel import Kernel
from app.store.database import Database


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
        assert "CapabilityDeferred" in types
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

    async def test_pre_approved_skips_new_approval(self, tmp_path):
        k, _ = make_kernel(tmp_path)
        pending = await k.invoke_capability(
            "write_file", {"path": "/tmp/x", "content": "hi"}, actor="user", correlation_id="pre",
        )
        assert pending["status"] == "pending"
        approval_id = pending["approval_id"]

        k.grant_approval(approval_id, action="write_file", actor="user", reason="user_ok")
        result = await k.invoke_capability(
            "write_file",
            {"path": "/tmp/x", "content": "hi"},
            actor="user",
            correlation_id="pre_exec",
            pre_approved=True,
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
