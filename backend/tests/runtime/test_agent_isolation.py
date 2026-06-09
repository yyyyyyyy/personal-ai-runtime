"""Agent capability whitelist isolation."""

import os
import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.store.database import Database


@pytest.fixture
def kernel(tmp_path):
    return Kernel(db=Database(db_path=str(tmp_path / "iso.db")))


@pytest.mark.asyncio
async def test_planner_cannot_invoke_shell(kernel):
    k = kernel
    task = k.create_task("plan", actor="user")
    handle = k.spawn_agent(
        "planner", task["task_id"],
        allowed_capabilities=["get_current_time", "web_search"],
    )
    agent_actor = f"agent:{handle['agent_id']}"
    cap = await k.invoke_capability("shell_exec", {"command": "ls"}, actor=agent_actor)
    assert cap["status"] == "error"
    assert "not authorized" in cap.get("error", "").lower()
    k.kill_agent(handle)
