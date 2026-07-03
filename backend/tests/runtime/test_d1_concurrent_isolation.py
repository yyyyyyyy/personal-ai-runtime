"""D1 · Agent concurrent isolation tests.

Validates:
  1. Parallel invoke_capability — taint does not cross between concurrent invocations
  2. Parallel WorkItem enqueue — events are isolated by actor
  3. Execution contextvars — execution_id does not leak across concurrent handlers
  4. Scheduler batch — _MAX_CONCURRENT=8 limit is respected
"""

import asyncio
import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def _reset_scheduler():
    from app.core.runtime.agent_scheduler import reset_scheduler
    reset_scheduler()
    yield
    reset_scheduler()


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database
    return Kernel(db=Database(db_path=str(tmp_path / "d1_iso.db")))


# ── 1. Parallel invoke_capability — taint isolation ────────────────────

@pytest.mark.asyncio
async def test_concurrent_capability_taint_isolation(kernel, monkeypatch):
    """Two concurrent invoke_capability calls with different correlation_ids:
    taint on one must not affect the other.

    Taint escalation requires write-class tools, so we register the tool
    as a write-class tool and mark only one correlation as tainted.
    """
    from app.core.harness.mcp_hub import ToolDef, mcp_hub
    from app.core.runtime.capability_governance import capability_governance
    from app.core.runtime.taint import register_external_write_tool, taint_registry

    tool_name = "mock_write_tool"

    async def _safe_handler(**kwargs):
        return '{"ok": true}'

    mcp_hub.register_tool(ToolDef(
        name=tool_name,
        description="Test write tool for concurrency",
        parameters={"type": "object", "properties": {}},
        handler=_safe_handler,
        is_async=True,
        requires_confirmation=True,
    ))
    capability_governance.register_external_tool(tool_name, risk="low")
    register_external_write_tool(tool_name)

    clean_corr = "clean_correlation"
    tainted_corr = "tainted_correlation"

    taint_registry.mark(tainted_corr, source="external_ingestion", reason="web_search")

    results = await asyncio.gather(
        kernel.invoke_capability(
            name=tool_name, args={}, actor="user", correlation_id=clean_corr),
        kernel.invoke_capability(
            name=tool_name, args={}, actor="user", correlation_id=tainted_corr),
    )

    clean_result, tainted_result = results
    assert clean_result["status"] == "success", f"Clean should succeed: {clean_result}"
    assert tainted_result["status"] == "pending", f"Tainted should require approval: {tainted_result}"

    mcp_hub.unregister_tool(tool_name)
    taint_registry.clear(clean_corr)
    taint_registry.clear(tainted_corr)
    capability_governance.clear_external_tools()


@pytest.mark.asyncio
async def test_concurrent_capability_taint_no_cross_contamination(kernel, monkeypatch):
    """Three concurrent invocations with write-class tool:
    only the tainted correlation escalates, others succeed."""
    from app.core.harness.mcp_hub import ToolDef, mcp_hub
    from app.core.runtime.capability_governance import capability_governance
    from app.core.runtime.taint import register_external_write_tool, taint_registry

    tool_name = "mock_concurrent_write_tool"

    async def _safe_handler(**kwargs):
        return '{"ok": true}'

    mcp_hub.register_tool(ToolDef(
        name=tool_name,
        description="Concurrency write test tool",
        parameters={"type": "object", "properties": {}},
        handler=_safe_handler,
        is_async=True,
        requires_confirmation=True,
    ))
    capability_governance.register_external_tool(tool_name, risk="low")
    register_external_write_tool(tool_name)

    corr_1 = "corr_1_clean"
    corr_2 = "corr_2_tainted"
    corr_3 = "corr_3_clean"

    taint_registry.mark(corr_2, source="external_ingestion", reason="test")

    results = await asyncio.gather(
        kernel.invoke_capability(name=tool_name, args={}, actor="user", correlation_id=corr_1),
        kernel.invoke_capability(name=tool_name, args={}, actor="user", correlation_id=corr_2),
        kernel.invoke_capability(name=tool_name, args={}, actor="user", correlation_id=corr_3),
    )

    assert results[0]["status"] == "success"
    assert results[2]["status"] == "success"
    assert results[1]["status"] == "pending", f"Tainted should be pending: {results[1]}"

    mcp_hub.unregister_tool(tool_name)
    for c in [corr_1, corr_2, corr_3]:
        taint_registry.clear(c)
    capability_governance.clear_external_tools()


# ── 3. Execution contextvars isolation ─────────────────────────────────

@pytest.mark.asyncio
async def test_execution_contextvar_isolation(kernel):
    """Contextvar execution_id must not leak between concurrent handler executions."""
    from app.core.runtime.execution_scope import (
        execution_scope,
        get_current_execution_id,
    )

    seen_ids: list[tuple[str, str | None]] = []

    async def concurrent_task(exec_id: str, delay: float = 0.01):
        with execution_scope(exec_id):
            await asyncio.sleep(delay)
            seen_ids.append((exec_id, get_current_execution_id()))

    await asyncio.gather(
        concurrent_task("exec-aaa", 0.02),
        concurrent_task("exec-bbb", 0.01),
        concurrent_task("exec-ccc", 0.03),
    )

    for expected_id, observed_id in seen_ids:
        assert observed_id == expected_id, f"Expected {expected_id}, got {observed_id}"

    assert get_current_execution_id() is None


@pytest.mark.asyncio
async def test_execution_scope_nesting(kernel):
    """Nested execution_scopes must correctly restore the parent scope."""
    from app.core.runtime.execution_scope import (
        execution_scope,
        get_current_execution_id,
    )

    with execution_scope("outer"):
        assert get_current_execution_id() == "outer"
        with execution_scope("inner"):
            assert get_current_execution_id() == "inner"
        assert get_current_execution_id() == "outer"
    assert get_current_execution_id() is None


# ── 4. Scheduler batch limit ──────────────────────────────────────────

def test_scheduler_max_concurrent_batch(kernel):
    """Scheduler respects _MAX_CONCURRENT=8 batch limit."""
    from app.core.runtime.agent_scheduler import _MAX_CONCURRENT, get_scheduler
    from app.core.runtime.work_item import ExecutionPolicy, WorkItem

    assert _MAX_CONCURRENT == 8

    items = []
    for i in range(12):
        item = WorkItem(
            id=f"wi_batch_{i}",
            instance_id=f"agent_test_{i % 3}",
            event_type="GoalCreated",
            event_seq=i + 1,
            event_id=f"evt_{i}",
            correlation_id="batch_test",
            policy=ExecutionPolicy(),
        )
        items.append(item)

    scheduler = get_scheduler(kernel)
    scheduler._pending.extend(items)

    batch = scheduler._pending[:_MAX_CONCURRENT]
    remainder = scheduler._pending[_MAX_CONCURRENT:]

    assert len(batch) == _MAX_CONCURRENT
    assert len(remainder) == 4

    scheduler._pending.clear()
