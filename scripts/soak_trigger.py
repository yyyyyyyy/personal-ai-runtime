"""Lane A soak — ScheduledExecution accumulation (no AgentDefinition).

    emit → Scheduler.enqueue (fan-out) → handler_executions + Execution* events

Exit non-zero if terminal counts do not cover the batch (consistency gate).

Usage:
    cd backend
    python ../scripts/soak_trigger.py
    python ../scripts/soak_trigger.py 100
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

os.environ.setdefault("LLM_API_KEY", "soak-trigger")

from app.core.runtime.agent_scheduler import (  # noqa: E402
    get_scheduler,
    reset_scheduler,
)
from app.core.runtime.handler_registry import _registry, subscribe  # noqa: E402
from app.core.runtime.kernel_instance import kernel  # noqa: E402
from app.core.runtime.scheduled_execution import ExecutionPolicy  # noqa: E402

_fail_rates: dict[str, float] = {}
SOAK_EVENT_TYPE = "SoakTrigger"
_RUNTIME_ID = "runtime:primary"


def _register_handler(fail_rate: float = 0.0) -> None:
    _registry.pop(SOAK_EVENT_TYPE, None)
    _fail_rates[SOAK_EVENT_TYPE] = fail_rate

    @subscribe(SOAK_EVENT_TYPE)
    async def _on_soak(_ctx, _event):
        import random

        if random.random() < _fail_rates.get(SOAK_EVENT_TYPE, 0.0):
            raise RuntimeError("soak injected transient failure")


async def run_batch(n: int) -> int:
    reset_scheduler()

    fail_rate = 0.3 if (n // 10) % 7 == 6 else 0.0
    _register_handler(fail_rate)

    scheduler = get_scheduler(kernel)
    await scheduler.start()

    enqueued_ids: list[str] = []
    for i in range(n):
        policy = (
            ExecutionPolicy(max_retries=3, retry_delay_seconds=0.01)
            if fail_rate > 0
            else ExecutionPolicy.default()
        )
        event = kernel.emit_event(
            SOAK_EVENT_TYPE,
            "task",
            f"soak_task_{uuid.uuid4().hex[:8]}",
            payload={"index": i, "batch": n},
            actor="soak_script",
        )
        items = scheduler.enqueue(_RUNTIME_ID, _RUNTIME_ID, event, policy=policy)
        enqueued_ids.extend(it.id for it in items)
        if i % 10 == 9:
            await scheduler.flush()

    await scheduler.flush()
    await scheduler.stop()

    items = [kernel.read_scheduled_execution(eid) for eid in enqueued_ids]
    items = [it for it in items if it is not None]
    completed = sum(1 for it in items if it.status == "completed")
    failed = sum(1 for it in items if it.status == "failed")
    in_flight = sum(1 for it in items if it.status in ("pending", "running", "retrying"))

    print(f"\n{'=' * 55}")
    print(f"Soak batch: {n} events → {len(enqueued_ids)} ScheduledExecutions")
    print(f"{'=' * 55}")
    print(f"  completed:      {completed}")
    print(f"  failed:         {failed}")
    print(f"  in_flight:      {in_flight}")
    print(f"  fail_rate:      {fail_rate:.0%}")

    _registry.pop(SOAK_EVENT_TYPE, None)

    # Consistency gate: every enqueued execution must be terminal.
    ok = (
        len(enqueued_ids) >= n
        and len(items) == len(enqueued_ids)
        and completed + failed == len(enqueued_ids)
        and in_flight == 0
    )
    # Projection spot-check: random sample matches read_by_id.
    if items:
        sample = items[0]
        again = kernel.read_scheduled_execution(sample.id)
        ok = ok and again is not None and again.status == sample.status

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(f"Triggering {n} soak ScheduledExecutions...")
    raise SystemExit(asyncio.run(run_batch(n)))


if __name__ == "__main__":
    main()
