"""Regression test for ARCHITECTURE_SURVIVAL_REVIEW Critical #2.

The bug: ``builtin_tools/goals.py`` previously called ``kernel.emit_event``
directly, bypassing ``kernel.invoke_capability``'s 3-gate authorization.
``requires_confirmation=True`` on the tool registration had no effect
because the gate was never entered.

The fix: ``GoalsServer`` methods now route through ``invoke_capability``
and emit ``CapabilityInvoked`` on success; the actual emit_event side
effects live in ``_writer_*`` functions that run only after the gate allows.

This test pins the contract: any goal write through the LLM-facing API
MUST produce a Capability* event. If a future refactor re-introduces a
direct emit path, the assertion that no WorkItem* event exists without
a paired CapabilityInvoked will fail.
"""
import json
import os

os.environ.setdefault("LLM_API_KEY", "test-key")

import pytest

from app.core.harness.builtin_tools.goals import GoalsServer
from app.core.harness.mcp_hub import mcp_hub
from app.core.runtime.kernel import Kernel
from app.store.database import Database


@pytest.fixture
def isolated_kernel(tmp_path, monkeypatch):
    """Build a fresh Kernel + Database and bind it as the kernel_instance."""
    db = Database(db_path=str(tmp_path / "critical2.db"))
    k = Kernel(db=db)

    import app.core.runtime.kernel_instance as ki
    monkeypatch.setattr(ki, "kernel", k)
    # mcp_hub holds handlers that do lazy `from ... import kernel`, so no
    # direct monkeypatch is needed there — each call re-imports the singleton.
    yield k


def test_goals_tools_are_registered_with_writer_handlers():
    """The 3 goal-write tools must be registered with the writer functions,
    not GoalsServer methods, otherwise invoke_capability recursion would
    occur (the gate calls the handler, which would call the gate again)."""
    for name in ("create_goal", "update_goal_progress", "complete_goal"):
        tool = mcp_hub.get_tool(name)
        assert tool is not None, f"{name} must be registered"
        handler_name = getattr(tool.handler, "__name__", "")
        assert handler_name.startswith("_writer_"), (
            f"{name} handler must be a _writer_* function (got {handler_name}); "
            "otherwise invoke_capability would not reach the actual emit."
        )


@pytest.mark.asyncio
async def test_create_goal_emits_capability_invoked(isolated_kernel):
    """Critical #2 closure: create_goal must go through invoke_capability.

    Auto-allow is impossible (the policy marks it needs_user), so without
    pre-approval the gate defers and we see CapabilityDeferred. That is the
    contract we pin: the gate was actually entered.
    """
    server = GoalsServer()
    result = await server.create_goal(title="ship v0.3.0", importance=0.9)

    # The policy says needs_user — without an approval the call defers.
    # Either way, a Capability* event MUST exist (gate was entered).
    cap_events = [
        e for e in isolated_kernel.read_events()
        if e.type in {"CapabilityInvoked", "CapabilityDeferred", "CapabilityDenied"}
    ]
    assert len(cap_events) >= 1, (
        "create_goal did not produce a Capability* event — the 3-gate was "
        "bypassed. This is the Critical #2 regression."
    )
    # No WorkItem* event should exist yet when the call defers.
    work_events = [
        e for e in isolated_kernel.read_events()
        if e.type.startswith("WorkItem")
    ]
    assert work_events == [], (
        "WorkItem event emitted before the gate allowed — direct emit path "
        "regression (Critical #2 not fixed)."
    )


def test_writer_create_goal_emits_work_item(isolated_kernel):
    """The writer handler (registered as the tool's actual handler) emits
    WorkItemCreated when invoked directly — this is what runs after
    invoke_capability's gate allows. Verifies the emit side effect lives here
    (and only here), not in GoalsServer."""
    from app.core.harness.builtin_tools.goals import _writer_create_goal

    result_json = _writer_create_goal(title="writer goal", importance=0.8)
    result = json.loads(result_json)
    assert result["status"] == "created"

    events = isolated_kernel.read_events()
    types = [e.type for e in events]
    assert "WorkItemCreated" in types
    # The work item carries the goal-unification fields.
    work_event = next(e for e in events if e.type == "WorkItemCreated")
    assert work_event.payload["work_type"] == "goal"
    assert work_event.payload["title"] == "writer goal"
    assert work_event.payload["importance"] == 0.8
