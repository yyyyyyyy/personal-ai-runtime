"""Integration test: resolve_approval must execute the governed approval record."""

import asyncio
import json
import os

import pytest
from starlette.testclient import TestClient

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def _reset_scheduler():
    """Reset the global scheduler singleton and stale WorkItems between tests.

    The Scheduler is a singleton whose _pending list carries over
    recovered WorkItems from previous test runs.  Without this fixture,
    stale events (e.g. BackgroundTaskRequested from another test) are
    processed by the scheduler loop, monkeypatch the mock and cause the
    current test to see wrong captured values.
    """
    from app.core.runtime import agent_bootstrap
    from app.core.runtime.agent_scheduler import reset_scheduler
    from app.core.runtime.kernel_instance import kernel

    reset_scheduler()
    agent_bootstrap._spawned = False

    # Kill stale CHAT agent so ensure_agent() won't hit max_instances
    for inst in list(kernel.agent_registry._instances.values()):
        if inst.definition.agent_id == "chat_v1":
            kernel.agent_registry._instances.pop(inst.instance_id, None)

    # Clean up stale handler_executions that would be recovered by the
    # fresh scheduler, since they reference events from other test runs.
    try:
        from app.store.database import db
        with db.get_db() as conn:
            conn.execute("DELETE FROM handler_executions")
    except Exception:
        pass
    yield
    reset_scheduler()
    agent_bootstrap._spawned = False
    for inst in list(kernel.agent_registry._instances.values()):
        if inst.definition.agent_id == "chat_v1":
            kernel.agent_registry._instances.pop(inst.instance_id, None)
    try:
        from app.store.database import db
        with db.get_db() as conn:
            conn.execute("DELETE FROM handler_executions")
    except Exception:
        pass


def _pending_write_file(kernel):
    return asyncio.run(
        kernel.invoke_capability(
            "write_file",
            {"path": "/tmp/safe.txt", "content": "hello"},
            actor="user",
            correlation_id="approval-resolve-test",
        )
    )


def test_resolve_rejects_tampered_tool_name(client: TestClient):
    from app.core.runtime.kernel_instance import kernel

    pending = _pending_write_file(kernel)
    assert pending["status"] == "pending"
    approval_id = pending["approval_id"]

    r = client.post(
        f"/api/chat/approvals/{approval_id}/resolve",
        json={
            "decision": "approve",
            "tool_name": "shell_exec",
            "tool_args": {"command": "echo pwned"},
            "conv_id": "",
            "tool_call_id": "",
        },
    )
    assert r.status_code == 400
    assert "match" in r.json()["detail"].lower()


def test_resolve_rejects_already_resolved(client: TestClient):
    from app.core.runtime.kernel_instance import kernel

    pending = _pending_write_file(kernel)
    approval_id = pending["approval_id"]

    r1 = client.post(
        f"/api/chat/approvals/{approval_id}/resolve",
        json={"decision": "deny", "conv_id": "", "tool_call_id": ""},
    )
    assert r1.status_code == 200

    r2 = client.post(
        f"/api/chat/approvals/{approval_id}/resolve",
        json={"decision": "approve", "conv_id": "", "tool_call_id": ""},
    )
    assert r2.status_code == 409


def test_resolve_executes_server_record(client: TestClient, monkeypatch):
    from app.core.harness.mcp_hub import mcp_hub
    from app.core.runtime.kernel_instance import kernel

    captured: dict = {}

    async def fake_invoke(name, args):
        captured["name"] = name
        captured["args"] = args
        return json.dumps({"ok": True})

    monkeypatch.setattr(mcp_hub, "invoke_tool", fake_invoke)

    pending = _pending_write_file(kernel)
    approval_id = pending["approval_id"]

    r = client.post(
        f"/api/chat/approvals/{approval_id}/resolve",
        json={"decision": "approve", "conv_id": "", "tool_call_id": ""},
    )
    assert r.status_code == 200
    assert captured["name"] == "write_file"
    assert captured["args"] == {"path": "/tmp/safe.txt", "content": "hello"}
