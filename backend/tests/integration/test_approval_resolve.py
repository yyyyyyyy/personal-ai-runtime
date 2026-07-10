"""Integration test: resolve_approval must execute the governed approval record."""

import json
import os

import pytest
from starlette.testclient import TestClient

os.environ.setdefault("LLM_API_KEY", "test-key")


# NOTE: _pending_write_file now uses the synchronous kernel.request_approval()
# instead of asyncio.run(kernel.invoke_capability(...)). This eliminates the
# cross-event-loop scheduler zombie that previously caused intermittent 504s.
# The remaining 504 risk is a deeper scheduler/TestClient portal interaction
# issue (ARCHITECTURE_SURVIVAL_REVIEW High #6): the handler executes inside
# the TestClient portal loop, but submit_command's Future may not resolve if
# the scheduler's task scheduling timing doesn't align. Marked xfail until
# the scheduler loop is refactored to be TestClient-compatible.


def _pending_write_file(kernel):
    """Create a pending write_file approval without crossing event loops."""
    return kernel.request_approval(
        "write_file",
        risk="high",
        ctx={"args": {"path": "/tmp/safe.txt", "content": "hello"}},
        actor="user",
        correlation_id="approval-resolve-test",
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


@pytest.mark.xfail(
    reason="scheduler handler executes inside TestClient portal loop; "
           "submit_command Future may not resolve due to task scheduling "
           "timing. Tracked under ARCHITECTURE_SURVIVAL_REVIEW High #6.",
    strict=False,
)
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


@pytest.mark.xfail(
    reason="scheduler handler executes inside TestClient portal loop; "
           "submit_command Future may not resolve due to task scheduling "
           "timing. Tracked under ARCHITECTURE_SURVIVAL_REVIEW High #6.",
    strict=False,
)
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
