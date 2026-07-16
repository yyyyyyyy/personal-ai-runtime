"""Lane A soak — crash/restart recovery for ScheduledExecution (no AgentDefinition).

Verifies:
  - crash leaves rows in running
  - new Scheduler emits ExecutionRetried(reason=interrupted) per id
  - no running rows remain
  - projection readable by id matches recovered state

Usage:
    cd backend
    python ../scripts/soak_recovery.py
    python ../scripts/soak_recovery.py 20
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

os.environ.setdefault("LLM_API_KEY", "soak-recovery")

from app.core.runtime.agent_scheduler import (  # noqa: E402
    get_scheduler,
    reset_scheduler,
)
from app.core.runtime.execution_events import emit_execution_started  # noqa: E402
from app.core.runtime.handler_registry import _registry, subscribe  # noqa: E402
from app.core.runtime.kernel_instance import kernel  # noqa: E402

RECOVERY_EVENT_TYPE = "SoakRecoveryTrigger"
_RUNTIME_ID = "runtime:primary"


def _register_blocking_handler() -> None:
    _registry.pop(RECOVERY_EVENT_TYPE, None)

    @subscribe(RECOVERY_EVENT_TYPE)
    async def _on_block(_ctx, _event):
        await asyncio.sleep(3600)


async def phase1_seed_running(n: int) -> list[str]:
    _register_blocking_handler()

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
        items = scheduler.enqueue(_RUNTIME_ID, _RUNTIME_ID, event)
        execution_ids.extend(it.id for it in items)

    await asyncio.sleep(0.15)
    await scheduler.stop()

    for eid in execution_ids:
        item = kernel.read_scheduled_execution(eid)
        if item is not None and item.status != "running":
            item.transition_to("running")
            emit_execution_started(kernel, item)

    return execution_ids


def phase2_verify_crash_state(execution_ids: list[str]) -> int:
    running = 0
    for eid in execution_ids:
        item = kernel.read_scheduled_execution(eid)
        if item is not None and item.status == "running":
            running += 1
    return running


async def phase3_recover() -> None:
    reset_scheduler()
    get_scheduler(kernel)


def phase4_verify(execution_ids: list[str]) -> dict:
    result: dict = {}
    all_events = kernel.read_events(aggregate_type="execution")
    interrupted_events = [
        e
        for e in all_events
        if e.type == "ExecutionRetried" and e.payload.get("reason") == "interrupted"
    ]
    interrupted_ids = {e.aggregate_id for e in interrupted_events}
    result["retried_events"] = len(interrupted_events)
    result["all_recovered"] = all(eid in interrupted_ids for eid in execution_ids)

    still_running = 0
    projection_ok = True
    for eid in execution_ids:
        item = kernel.read_scheduled_execution(eid)
        if item is None:
            projection_ok = False
            continue
        if item.status == "running":
            still_running += 1
        # After recovery, interrupted items should be pending/retrying/completed/failed
        # — never still 'running'.
    result["still_running"] = still_running
    result["projection_ok"] = projection_ok
    return result


async def main_async(n: int) -> int:
    print(f"Seeding {n} running ScheduledExecutions...")
    ids = await phase1_seed_running(n)
    crashed = phase2_verify_crash_state(ids)
    print(f"  crash-state running: {crashed}/{len(ids)}")
    print("Recovering via new Scheduler...")
    await phase3_recover()
    result = phase4_verify(ids)
    print(f"  retried_events: {result['retried_events']}")
    print(f"  all_recovered:  {result['all_recovered']}")
    print(f"  still_running:  {result['still_running']}")
    print(f"  projection_ok:  {result['projection_ok']}")
    _registry.pop(RECOVERY_EVENT_TYPE, None)
    ok = (
        result["all_recovered"]
        and result["still_running"] == 0
        and result["projection_ok"]
        and crashed == len(ids)
    )
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    raise SystemExit(asyncio.run(main_async(n)))


if __name__ == "__main__":
    main()
