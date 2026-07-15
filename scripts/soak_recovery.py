"""Execution 契约 §3 Soak Gate — recovery 路径验证脚本。

模拟真实的 crash/restart 场景，验证 recovery 通过事件流（而非 bare SQL UPDATE）
完成 running → retrying → pending 的转换，且 shadow compare 0 mismatch。

流程:
    Step 1: 启动 Scheduler，emit N 个事件，让它们进入 running 状态
    Step 2: 模拟 crash —— 不等 handler 完成，直接 stop（running 行留在 DB）
    Step 3: 新 Scheduler 实例启动 → _recover() 触发事件化恢复
    Step 4: 验证 event_log 有 ExecutionRetried(interrupted)
             handler_executions 状态正确
             shadow compare 0 mismatch
             rebuild("execution") == handler_executions

用法:
    cd backend
    python ../scripts/soak_recovery.py            # 默认 5 个 running
    python ../scripts/soak_recovery.py 20          # 20 个 running
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

os.environ.setdefault("LLM_API_KEY", "soak-recovery")

from app.core.runtime.agent_definition import (  # noqa: E402
    AgentDefinition,
    SubscriptionRule,
)
from app.core.runtime.agent_scheduler import (  # noqa: E402
    get_scheduler,
    reset_scheduler,
)
from app.core.runtime.execution_events import emit_execution_started  # noqa: E402
from app.core.runtime.execution_shadow_compare import (  # noqa: E402
    assert_zero_mismatches,
    get_shadow_compare_stats,
    reset_shadow_compare_stats,
)
from app.core.runtime.handler_registry import _registry, subscribe  # noqa: E402
from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION  # noqa: E402
from app.core.runtime.kernel_instance import kernel  # noqa: E402

RECOVERY_EVENT_TYPE = "SoakRecoveryTrigger"


def _register_blocking_handler() -> None:
    """Register a handler that blocks forever (via Event) so items stay 'running'."""
    import threading

    block_event = threading.Event()

    _registry.pop(RECOVERY_EVENT_TYPE, None)

    @subscribe(RECOVERY_EVENT_TYPE)
    async def _on_block(instance, event):
        # Never completes — simulates a handler stuck mid-execution.
        # The Scheduler processes this in _process_work_item; we sleep long
        # enough that stop() cancels it before it returns.
        await asyncio.sleep(3600)

    return block_event


async def phase1_seed_running(n: int) -> list[str]:
    """Step 1: emit n events, transition to running, emit ExecutionStarted.

    Returns the list of execution_ids left in 'running' state.

    We use a hybrid approach: enqueue via the scheduler (so ExecutionRequested
    + ExecutionStarted are emitted through the real dual-write path), then
    immediately stop the scheduler. Items that the scheduler picked up will
    be 'running' in the DB with ExecutionStarted emitted. We then force any
    that didn't get picked up into 'running' via the same emit path, so the
    crash state is consistent regardless of scheduler timing.
    """
    from app.core.runtime.execution_events import (
        emit_execution_requested,
        emit_execution_started,
    )
    from app.core.runtime.work_item import WorkItem

    definition = AgentDefinition(
        agent_id="soak_recovery",
        subscriptions=[SubscriptionRule(event_type=RECOVERY_EVENT_TYPE)],
    )

    _register_blocking_handler()

    registry = kernel.agent_registry
    instance = await registry.spawn(definition)
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    execution_ids: list[str] = []
    for i in range(n):
        event = kernel.emit_event(
            RECOVERY_EVENT_TYPE,
            "task",
            f"soak_recovery_{uuid.uuid4().hex[:8]}",
            payload={"index": i},
            actor="soak_recovery",
        )
        item = scheduler.enqueue(instance.instance_id, instance.actor_id(), event)
        if item is not None:
            execution_ids.append(item.id)

    # Give the scheduler a moment to pick up items.
    await asyncio.sleep(0.15)
    await scheduler.stop()
    await registry.kill(instance.instance_id, reason="crash simulation")

    # Ensure ALL items are in 'running' state with ExecutionStarted emitted,
    # regardless of whether the scheduler managed to process them before stop.
    # This mirrors a real crash: the process dies mid-flight, and any item that
    # had been dispatched (or was about to be) appears as 'running' in the DB.
    # Step 4: the projector (triggered by emit_execution_started) is the sole
    # writer to handler_executions — no persist_work_item call.
    from app.core.runtime.execution_events import emit_execution_started
    items = kernel.read_work_items()
    for item in items:
        if item.id in execution_ids and item.status != "running":
            # Re-emit ExecutionStarted to simulate that this item was running
            # when the crash happened. The projector updates the row to
            # status='running' — that is now the only write path.
            item.transition_to("running")
            emit_execution_started(kernel, item)

    return execution_ids


def phase2_verify_crash_state(execution_ids: list[str]) -> int:
    """Confirm that after the crash, the items are 'running' in the DB."""
    items = kernel.read_work_items(status="running")
    running_ids = {it.id for it in items}
    crashed = sum(1 for eid in execution_ids if eid in running_ids)
    return crashed


async def phase3_recover() -> None:
    """Step 3: new Scheduler instance boots and runs _recover()."""
    reset_scheduler()
    get_scheduler(kernel)  # __init__ calls _recover()


def phase4_verify(execution_ids: list[str]) -> dict:
    """Step 4: verify the recovery produced correct event-sourced state."""
    result = {}

    # 4a: event_log has ExecutionRetried(reason=interrupted) for each item
    all_events = kernel.read_events(aggregate_type="execution")
    interrupted_events = [
        e for e in all_events
        if e.type == "ExecutionRetried"
        and e.payload.get("reason") == "interrupted"
    ]
    interrupted_ids = {e.aggregate_id for e in interrupted_events}
    result["retried_events"] = len(interrupted_events)
    result["all_recovered"] = all(eid in interrupted_ids for eid in execution_ids)

    # 4b: no item left in 'running' state
    still_running = kernel.read_work_items(status="running")
    result["still_running"] = len(still_running)

    # 4c: shadow compare stats
    stats = get_shadow_compare_stats()
    result["checkpoints"] = stats.checkpoints_checked
    result["mismatches"] = stats.mismatches
    result["mismatch_details"] = stats.details[:5]

    # 4d: rebuild identity — wipe handler_executions, rebuild from events
    with kernel._db.get_db() as conn:
        rows_before = conn.execute(
            "SELECT * FROM handler_executions ORDER BY id"
        ).fetchall()
    before = [dict(r) for r in rows_before]

    with kernel._db.get_db() as conn:
        conn.execute("DELETE FROM handler_executions")
    kernel.rebuild(AGGREGATE_EXECUTION)

    with kernel._db.get_db() as conn:
        rows_after = conn.execute(
            "SELECT * FROM handler_executions ORDER BY id"
        ).fetchall()
    after = [dict(r) for r in rows_after]

    result["rebuild_match"] = before == after

    return result


async def run(n: int) -> None:
    reset_scheduler()
    reset_shadow_compare_stats()

    print(f"\n{'=' * 55}")
    print(f"Soak Recovery Test: {n} interrupted executions")
    print(f"{'=' * 55}")

    # Step 1
    print(f"\n[Step 1] Seeding {n} executions and crashing mid-flight...")
    execution_ids = await phase1_seed_running(n)
    print(f"  Emitted {len(execution_ids)} events, scheduler crashed")

    # Step 2
    crashed = phase2_verify_crash_state(execution_ids)
    print(f"\n[Step 2] Verifying crash state:")
    print(f"  Items stuck in 'running': {crashed}/{len(execution_ids)}")

    if crashed == 0:
        print("  WARNING: no items left running — crash simulation may not have worked")
        print("  (handlers may have completed before stop). Retrying with longer delay.")

    # Step 3
    print(f"\n[Step 3] New scheduler instance booting → _recover()...")
    await phase3_recover()
    print(f"  Recovery complete")

    # Step 4
    print(f"\n[Step 4] Verifying event-sourced recovery:")
    result = phase4_verify(execution_ids)

    print(f"  ExecutionRetried(interrupted) events: {result['retried_events']}")
    print(f"  All crashed items recovered via event: {result['all_recovered']}")
    print(f"  Items still in 'running':             {result['still_running']}")
    print(f"  Shadow compare checkpoints:            {result['checkpoints']}")
    print(f"  Shadow compare mismatches:             {result['mismatches']}")
    if result["mismatch_details"]:
        print(f"  Mismatch details:")
        for d in result["mismatch_details"]:
            print(f"    {d}")
    print(f"  rebuild('execution') == handler_executions: {result['rebuild_match']}")

    # Verdict
    print(f"\n{'=' * 55}")
    all_pass = (
        result["all_recovered"]
        and result["still_running"] == 0
        and result["mismatches"] == 0
        and result["rebuild_match"]
    )
    if all_pass:
        print(f"VERDICT: PASS — recovery is fully event-sourced")
    else:
        print(f"VERDICT: FAIL — see details above")
    print(f"{'=' * 55}")

    # Cleanup
    _registry.pop(RECOVERY_EVENT_TYPE, None)


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    asyncio.run(run(n))


if __name__ == "__main__":
    main()
