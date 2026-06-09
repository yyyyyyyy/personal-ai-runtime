"""Executor routes tool calls through Kernel."""

import os
import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.store.database import Database


@pytest.fixture
def kernel(tmp_path):
    return Kernel(db=Database(db_path=str(tmp_path / "exec.db")))


@pytest.mark.asyncio
async def test_write_file_produces_approval_event(kernel, monkeypatch):
    from app.core.runtime import executor as exec_mod
    from app.core.runtime.kernel_instance import kernel as global_kernel

    monkeypatch.setattr(exec_mod, "kernel", kernel)
    monkeypatch.setattr(exec_mod, "db", kernel._db)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", kernel)

    kernel.emit_event("GoalCreated", "goal", "g1", {"title": "G"}, actor="user")
    kernel.emit_event(
        "ActionCreated", "action", "a1",
        {
            "goal_id": "g1",
            "title": "test",
            "status": "pending",
            "executable_plan": '{"steps":[{"tool":"write_file","params":{"path":"/tmp/t","content":"x"}}]}',
        },
        actor="user",
    )

    result = await exec_mod.executor.execute_action("a1")
    assert result["action_id"] == "a1"
    events = kernel.read_events(type="ApprovalRequested")
    assert len(events) >= 1
