"""ADR-0007 Step 3 Soak Gate 统计查询。

用法:
    cd backend
    python ../scripts/soak_stats.py

显示:
    - handler_executions 状态分布
    - completed executions 进度 (soak gate 基准: 100)
    - recovery ExecutionRetried(interrupted) 事件数
    - execution 事件类型分布
"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.store.database import db  # noqa: E402

BAR_LEN = 30


def main() -> None:
    print("=" * 55)
    print("ADR-0007 Step 3 Soak Gate 统计")
    print("=" * 55)

    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM handler_executions "
            "GROUP BY status ORDER BY c DESC"
        ).fetchall()
        print("\nhandler_executions 状态分布:")
        total = 0
        for r in rows:
            print(f"  {r['status']:12s}  {r['c']}")
            total += r["c"]
        print(f"  {'TOTAL':12s}  {total}")

        completed = conn.execute(
            "SELECT COUNT(*) FROM handler_executions WHERE status = 'completed'"
        ).fetchone()[0]

        retried = conn.execute(
            "SELECT COUNT(*) FROM event_log "
            "WHERE type = 'ExecutionRetried' "
            "AND json_extract(payload, '$.reason') = 'interrupted'"
        ).fetchone()[0]

        print(f"\nCompleted executions (soak 基准): {completed} / 100")
        print(f"Recovery ExecutionRetried(interrupted): {retried}")

        exec_events = conn.execute(
            "SELECT type, COUNT(*) AS c FROM event_log "
            "WHERE aggregate_type = 'execution' "
            "GROUP BY type ORDER BY c DESC"
        ).fetchall()
        print("\nExecution 事件分布:")
        for r in exec_events:
            print(f"  {r['type']:24s}  {r['c']}")

    print("\nSoak 进度 (executions):")
    pct = min(completed, 100)
    filled = int(BAR_LEN * pct / 100)
    bar = "#" * filled + "-" * (BAR_LEN - filled)
    print(f"  [{bar}] {completed}/100")

    print("\nSoak 进度 (天数):")
    print("  开始: 2026-06-15")
    print("  需要: >= 7 个自然日 (即 >= 2026-06-22)")
    print("  或:   >= 100 completed executions")
    print("  取较晚者")

    print("\nShadow mismatch:")
    print("  运行时累积在内存 (ShadowCompareStats)，重启后清零")
    print("  监控方式: 查日志关键词")
    print('    "Execution shadow compare mismatch for wi_*"')
    print("  或定期跑测试:")
    print("    pytest backend/tests/runtime/test_execution_shadow_compare.py")


if __name__ == "__main__":
    main()
