"""开发期 dogfood soak 报告（只读）。

对当前 backend/data/personal_ai.db 输出只读计数报告，用于核对
docs/05-engineering/development.md「开发期自用检查」表中的主观判断
是否与库内数据一致。

用法:
    python scripts/soak_dogfood_report.py
    python scripts/soak_dogfood_report.py --db path/to/other.db

设计约束:
    - 只读，不触发应用初始化、不写库、不进 CI。
    - 直接用 sqlite3 标准库，避免 import app.* 带来的副作用。
    - 任何表/列缺失时降级为 SKIP 而非崩溃（兼容历史 DB 与 verify 残留库）。
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "backend" / "data" / "personal_ai.db"


def _count(conn: sqlite3.Connection, table: str) -> int | str:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.Error:
        return "SKIP (table missing)"


def _count_where(conn: sqlite3.Connection, table: str, where: str) -> int | str:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]
    except sqlite3.Error:
        return "SKIP (table/column missing)"


def _count_stale_approvals(conn: sqlite3.Connection) -> int | str:
    """Count pending approvals past their expires_at.

    expires_at is stored as ISO-8601 with offset (e.g. '2026-07-12T11:58:45+00:00').
    SQLite's datetime() returns 'YYYY-MM-DD HH:MM:SS' (space separator, no tz),
    so a string compare is unreliable. Parse in Python with datetime.fromisoformat
    (3.11+ handles offsets) and compare in UTC.
    """
    from datetime import datetime, timezone

    try:
        rows = conn.execute(
            "SELECT expires_at FROM approvals WHERE status = 'pending' AND expires_at IS NOT NULL"
        ).fetchall()
    except sqlite3.Error:
        return "SKIP (table/column missing)"

    now = datetime.now(timezone.utc)
    stale = 0
    for (raw,) in rows:
        try:
            exp = datetime.fromisoformat(raw)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp <= now:
                stale += 1
        except (ValueError, TypeError):
            continue
    return stale


def _recent_events(conn: sqlite3.Connection, limit: int = 3) -> list[str]:
    """Return formatted lines for the newest event_log rows (seq, type, ts)."""
    try:
        rows = conn.execute(
            "SELECT seq, type, ts FROM event_log ORDER BY seq DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [f"seq={r[0]}  type={r[1]}  ts={r[2]}" for r in rows]
    except sqlite3.Error:
        return []


def _section(title: str) -> None:
    print()
    print("-" * 55)
    print(title)
    print("-" * 55)


def report(db_path: Path) -> int:
    if not db_path.exists():
        print(f"DB not found: {db_path}")
        return 1

    # mode=ro: 禁止任何写入，即使脚本有 bug 也不会污染库。
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        print("=" * 55)
        print("开发期 Dogfood Soak 报告")
        print(f"DB: {db_path}")
        print(f"Size: {db_path.stat().st_size / 1024:.0f} KB")
        print("=" * 55)

        _section("核心计数")
        core_tables = [
            "event_log",
            "conversations",
            "messages",
            "memories",
            "work_items",
            "approvals",
            "notifications",
            "inbox_emails",
            "handler_executions",
            "tool_calls",
            "llm_calls",
        ]
        for t in core_tables:
            print(f"  {t:22s} {_count(conn, t)}")

        _section("工具审批闭环（dogfood: Chat pass 证据）")
        approved = _count_where(conn, "approvals", "status='approved'")
        pending = _count_where(conn, "approvals", "status='pending'")
        cap_invoked = _count_where(conn, "event_log", "type='CapabilityInvoked'")
        print(f"  approvals total          {_count(conn, 'approvals')}")
        print(f"  approvals approved       {approved}")
        print(f"  approvals pending        {pending}")
        print(f"  CapabilityInvoked events {cap_invoked}")

        _section("记忆闭环（dogfood: Memory pass 证据）")
        mem_derived = _count_where(conn, "event_log", "type='MemoryDerived'")
        mem_updated = _count_where(conn, "event_log", "type='MemoryUpdated'")
        print(f"  memories total           {_count(conn, 'memories')}")
        print(f"  MemoryDerived events     {mem_derived}")
        print(f"  MemoryUpdated events     {mem_updated}")

        _section("Work items（dogfood: Work pass 证据）")
        wi_completed = _count_where(conn, "work_items", "status='completed'")
        wi_progress = _count_where(conn, "work_items", "status='in_progress'")
        print(f"  work_items total         {_count(conn, 'work_items')}")
        print(f"  completed                {wi_completed}")
        print(f"  in_progress              {wi_progress}")

        _section("Inbox（dogfood: Inbox 状态）")
        print(f"  inbox_emails total       {_count(conn, 'inbox_emails')}")
        print("  若为 0 且未接 Gmail → 记 blocked，非 fail")

        _section("异常信号（仅提示，非阻断）")
        conv = _count(conn, "conversations")
        msgs = _count(conn, "messages")
        if isinstance(conv, int) and isinstance(msgs, int) and conv > 5 and msgs < conv:
            print(f"  ! conversations={conv} 但 messages={msgs}：对话多而消息少，可能 chat 未真日用")
        else:
            print("  conversations/messages 比例正常或数据不足")

        repairs = _count(conn, "memory_index_repairs")
        if isinstance(repairs, int) and repairs > 0:
            print(f"  ! memory_index_repairs={repairs}：有待修复的向量索引（RuntimeLoop 会重试）")

        stale_appr = _count_stale_approvals(conn)
        if isinstance(stale_appr, int) and stale_appr > 0:
            print(
                f"  ! {stale_appr} 个 approval 已过期但仍 pending：RuntimeLoop 未在跑"
                "（开发期常见，跑测试/verify 后 Kernel 关闭，过期清理 tick 没执行）。"
                "重启后端会自动 expire；非数据问题。"
            )

        _section("最近活动（最新 3 条 event_log）")
        recent = _recent_events(conn)
        if recent:
            for line in recent:
                print(f"  {line}")
        else:
            print("  (无法读取 event_log)")

        print()
        print("解读：对照 development.md「开发期自用检查」表填写本周状态。")
        print("此报告不进 CI，不写库；可本地保留或贴进 PR 描述。")
        return 0
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="开发期 dogfood soak 只读报告")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite DB 路径")
    args = parser.parse_args()
    sys.exit(report(args.db))


if __name__ == "__main__":
    main()
