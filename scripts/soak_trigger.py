"""ADR-0007 Step 3 Soak Gate — execution 累积脚本。

每次运行产生 N 个真实 execution，完整走 Scheduler 闭环：
    emit(TaskCreated) → AgentBus → AgentInstance.dispatch
        → Scheduler.enqueue → _persist_emit_verify
        → handler_executions + event_log + shadow compare

用法:
    cd backend
    python ../scripts/soak_trigger.py            # 默认跑 10 个
    python ../scripts/soak_trigger.py 100         # 跑 100 个

每个 execution 的 handler 是 no-op（不调 LLM），所以速度很快。
故意让其中一些失败+重试，覆盖 retry 路径的 shadow compare。

跑完后可以查看统计:
    python ../scripts/soak_stats.py
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
from app.core.runtime.execution_shadow_compare import (  # noqa: E402
    assert_zero_mismatches,
    get_shadow_compare_stats,
    reset_shadow_compare_stats,
)
from app.core.runtime.handler_registry import _registry, subscribe  # noqa: E402
from app.core.runtime.kernel_instance import kernel  # noqa: E402
from app.core.runtime.work_item import ExecutionPolicy  # noqa: E402

# --- soak handler ---------------------------------------------------------

_fail_rates: dict[str, float] = {}

# 用一个独特的 event type，避免和其他 handler 的 TaskCreated 冲突。
# 但 Scheduler 只认 handler_registry 里的注册，所以我们用自己的 type。
SOAK_EVENT_TYPE = "SoakTrigger"


def _register_handler(fail_rate: float = 0.0) -> None:
    """Register (or re-register) the soak handler with a given fail rate."""
    _registry.pop(SOAK_EVENT_TYPE, None)
    _fail_rates[SOAK_EVENT_TYPE] = fail_rate

    @subscribe(SOAK_EVENT_TYPE)
    async def _on_soak(instance, event):
        import random
        if random.random() < _fail_rates.get(SOAK_EVENT_TYPE, 0.0):
            raise RuntimeError("soak injected transient failure")


async def run_batch(n: int) -> None:
    from app.core.runtime.agent_definition import (
        AgentDefinition,
        SubscriptionRule,
    )
    from app.core.runtime.agent_scheduler import get_scheduler

    reset_scheduler()
    reset_shadow_compare_stats()

    definition = AgentDefinition(
        agent_id="soak_runner",
        subscriptions=[SubscriptionRule(event_type=SOAK_EVENT_TYPE)],
    )

    # Every 7th batch uses a higher fail rate to exercise the retry path.
    fail_rate = 0.3 if (n // 10) % 7 == 6 else 0.0
    _register_handler(fail_rate)

    registry = kernel.agent_registry
    instance = await registry.spawn(definition)
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    completed = 0
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
        scheduler.enqueue(instance.instance_id, instance.actor_id(), event, policy=policy)
        # Drain in small batches so the loop stays responsive.
        if i % 10 == 9:
            await scheduler.flush()

    await scheduler.flush()
    await scheduler.stop()
    await registry.kill(instance.instance_id, reason="soak complete")

    # Count results
    items = kernel.read_work_items()
    completed = sum(1 for it in items if it.status == "completed")
    failed = sum(1 for it in items if it.status == "failed")

    stats = get_shadow_compare_stats()
    print(f"\n{'=' * 55}")
    print(f"Soak batch: {n} executions")
    print(f"{'=' * 55}")
    print(f"  completed:      {completed}")
    print(f"  failed:         {failed}")
    print(f"  fail_rate:      {fail_rate:.0%}")
    print(f"  checkpoints:    {stats.checkpoints_checked}")
    print(f"  mismatches:     {stats.mismatches}")
    if stats.details:
        print(f"  details:")
        for d in stats.details[:10]:
            print(f"    {d}")

    try:
        assert_zero_mismatches()
        print(f"\n  SHADOW COMPARE: PASS (0 mismatches)")
    except AssertionError as exc:
        print(f"\n  SHADOW COMPARE: FAIL")
        print(f"  {exc}")

    _registry.pop(SOAK_EVENT_TYPE, None)


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(f"Triggering {n} soak executions...")
    asyncio.run(run_batch(n))


if __name__ == "__main__":
    main()
