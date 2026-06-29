"""Agent capability whitelist isolation (ADR-0007 Step 9/10)."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

import pytest

from app.core.runtime.kernel import Kernel
from app.store.database import Database


@pytest.fixture
def kernel(tmp_path):
    return Kernel(db=Database(db_path=str(tmp_path / "iso.db")))


@pytest.fixture
def execution_id(kernel):
    from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION, EVENT_EXECUTION_REQUESTED

    eid = "wi_iso"
    kernel.emit_event(
        EVENT_EXECUTION_REQUESTED,
        AGGREGATE_EXECUTION,
        eid,
        payload={
            "execution_id": eid,
            "handler_name": "on_test",
            "trigger_event_id": "evt_iso",
            "trigger_event_seq": 1,
            "trigger_event_type": "TaskCreated",
            "instance_id": "inst_iso",
            "policy": {},
            "event_seq": 1,
        },
        actor="scheduler",
    )
    return eid


@pytest.mark.asyncio
async def test_planner_cannot_invoke_shell(kernel, execution_id):
    """AgentRegistry path: restricted agent cannot invoke unlisted capability."""
    from app.core.runtime.agent_definition import AgentDefinition

    restricted_def = AgentDefinition(
        agent_id="planner_v1",
        tools=["get_current_time", "web_search"],
        subscriptions=[],
    )
    registry = kernel.agent_registry
    instance = await registry.spawn(restricted_def)
    agent_actor = f"agent:{instance.instance_id}"

    cap = await kernel.invoke_capability(
        "shell_exec", {"command": "ls"}, actor=agent_actor, execution_id=execution_id,
    )
    assert cap["status"] == "error"
    assert "principal_not_authorized" in cap.get("error", "")

    await registry.kill(instance.instance_id)


@pytest.mark.asyncio
async def test_new_agent_instance_capability_isolation_enforced(kernel, execution_id):
    """ADR-0007 Step 9: fail-closed — restricted agent denied unlisted capability."""
    from app.core.runtime.agent_definition import AgentDefinition

    restricted_def = AgentDefinition(
        agent_id="restricted_v1",
        tools=["get_current_time"],
        subscriptions=[],
    )
    registry = kernel.agent_registry
    instance = await registry.spawn(restricted_def)
    agent_actor = f"agent:{instance.instance_id}"

    cap = await kernel.invoke_capability(
        "shell_exec", {"command": "ls"}, actor=agent_actor, execution_id=execution_id,
    )
    assert cap["status"] == "error"
    assert "principal_not_authorized" in cap.get("error", "")

    await registry.kill(instance.instance_id)


@pytest.mark.asyncio
async def test_new_agent_instance_allowed_capability_not_denied(kernel, execution_id):
    """An agent invoking a whitelisted capability must not be rejected."""
    from app.core.runtime.agent_definition import AgentDefinition

    def_with_time = AgentDefinition(
        agent_id="timeuser_v1",
        tools=["get_current_time"],
        subscriptions=[],
    )
    registry = kernel.agent_registry
    instance = await registry.spawn(def_with_time)
    agent_actor = f"agent:{instance.instance_id}"

    cap = await kernel.invoke_capability(
        "get_current_time", {}, actor=agent_actor, execution_id=execution_id,
    )
    denied = (
        cap.get("status") == "error"
        and "principal_not_authorized" in cap.get("error", "")
    )
    assert not denied, "Whitelisted capability was incorrectly denied"

    await registry.kill(instance.instance_id)
