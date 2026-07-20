"""D2 — execution_id runtime ownership enforcement."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

@pytest.fixture
def kernel(isolated_kernel):
    k, _db = isolated_kernel
    return k

@pytest.fixture(autouse=True)
def _reset_scheduler():
    from app.core.runtime.agent_scheduler import reset_scheduler

    reset_scheduler()
    yield
    reset_scheduler()

def _seed_execution(kernel, execution_id: str = "wi_test_ownership") -> None:
    from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION, EVENT_EXECUTION_REQUESTED

    kernel.emit_event(
        EVENT_EXECUTION_REQUESTED,
        AGGREGATE_EXECUTION,
        execution_id,
        payload={
            "execution_id": execution_id,
            "handler_name": "on_test",
            "trigger_event_id": "evt_seed",
            "trigger_event_seq": 1,
            "trigger_event_type": "TaskCreated",
            "instance_id": "inst_seed",
            "policy": {},
            "event_seq": 1,
        },
        actor="scheduler",
    )

@pytest.mark.asyncio
async def test_runtime_actor_denies_missing_execution_id(kernel):
    with patch(
        "app.core.harness.mcp_hub.mcp_hub.invoke_tool",
        new_callable=AsyncMock,
    ) as mock_invoke:
        result = await kernel.invoke_capability(
            "get_current_time",
            {},
            actor="scheduler",
            execution_id=None,
        )

    assert result["status"] == "error"
    assert result["error"] == "missing_execution_id"
    mock_invoke.assert_not_called()
    events = kernel.read_events(type="CapabilityDenied")
    assert any(e.payload.get("reason") == "missing_execution_id" for e in events)

@pytest.mark.asyncio
async def test_agent_actor_denies_missing_execution_id(kernel):
    with patch(
        "app.core.harness.mcp_hub.mcp_hub.invoke_tool",
        new_callable=AsyncMock,
    ) as mock_invoke:
        result = await kernel.invoke_capability(
            "get_current_time",
            {},
            actor="agent:test_agent",
            execution_id=None,
        )

    assert result["status"] == "error"
    assert result["error"] == "missing_execution_id"
    mock_invoke.assert_not_called()

@pytest.mark.asyncio
async def test_invalid_execution_id_denied(kernel):
    _seed_execution(kernel)
    with patch(
        "app.core.harness.mcp_hub.mcp_hub.invoke_tool",
        new_callable=AsyncMock,
    ) as mock_invoke:
        result = await kernel.invoke_capability(
            "get_current_time",
            {},
            actor="scheduler",
            execution_id="wi_nonexistent",
        )

    assert result["status"] == "error"
    assert result["error"] == "invalid_execution_id"
    mock_invoke.assert_not_called()

@pytest.mark.asyncio
async def test_user_actor_allows_missing_execution_id(kernel):
    with patch(
        "app.core.harness.mcp_hub.mcp_hub.invoke_tool",
        new_callable=AsyncMock,
        return_value="ok",
    ) as mock_invoke:
        result = await kernel.invoke_capability(
            "get_current_time",
            {},
            actor="user",
            execution_id=None,
        )

    assert result["status"] == "success"
    mock_invoke.assert_called_once()

@pytest.mark.asyncio
async def test_execution_scope_binds_capability_caused_by(kernel):
    from app.core.runtime.execution import execution_scope

    _seed_execution(kernel, "wi_scope_bind")

    with execution_scope("wi_scope_bind"):
        with patch(
            "app.core.harness.mcp_hub.mcp_hub.invoke_tool",
            new_callable=AsyncMock,
            return_value="ok",
        ):
            result = await kernel.invoke_capability(
                "get_current_time",
                {},
                actor="background",
                execution_id=None,
            )

    assert result["status"] == "success"
    invoked = [e for e in kernel.read_events(type="CapabilityInvoked")]
    assert invoked
    assert invoked[-1].caused_by == "wi_scope_bind"

@pytest.mark.asyncio
async def test_valid_execution_id_allows_runtime_actor(kernel):
    _seed_execution(kernel, "wi_valid")
    with patch(
        "app.core.harness.mcp_hub.mcp_hub.invoke_tool",
        new_callable=AsyncMock,
        return_value="ok",
    ) as mock_invoke:
        result = await kernel.invoke_capability(
            "get_current_time",
            {},
            actor="background",
            execution_id="wi_valid",
        )

    assert result["status"] == "success"
    mock_invoke.assert_called_once()
