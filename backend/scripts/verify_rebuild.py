#!/usr/bin/env python
"""Rebuild verification guard: replay the Event Log and verify projections.

This script emits a set of sample events, snapshots the projection tables,
performs a full rebuild, then asserts the post-rebuild state is identical.
Non-zero exit means the Event Log cannot reconstruct State — a Runtime invariant
violation that must block CI.
"""

from __future__ import annotations

from pathlib import Path

import sys
from typing import Any

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from scripts._bootstrap import ephemeral_kernel

SAMPLE_SCENARIO: list[tuple[str, str, str, dict[str, Any]]] = [
    # Goals
    ("WorkItemCreated", "work_item", "g1", {"title": "Project Alpha", "importance": 0.9}),
    ("WorkItemCreated", "work_item", "g2", {"title": "Learn Zig", "urgency": 0.7}),
    ("WorkItemUpdated", "work_item", "g1", {"progress": 0.5}),
    ("WorkItemStatusChanged", "work_item", "g2", {}),
    ("WorkItemDeleted", "work_item", "g1", {}),
    # Approvals
    ("ApprovalRequested", "approval", "apr1", {"action": "write_file", "risk": "high", "ctx": {}}),
    ("ApprovalGranted", "approval", "apr1", {}),
    # Memories
    ("MemoryDerived", "memory", "m1", {"category": "fact", "content": "Likes Rust", "confidence": 0.8}),
    ("MemoryUpdated", "memory", "m1", {"content": "Prefers Rust", "confidence": 0.9}),
    ("MemoryDeleted", "memory", "m1", {}),
    # WorkItem
    ("WorkItemCreated", "work_item", "wi1", {
        "title": "Ship feature",
        "description": "Build runtime",
        "work_type": "task",
        "parent_work_id": None,
        "parent_goal_id": None,
        "dependencies_json": None,
        "priority": 1,
        "status": "pending",
    }),
    ("WorkItemStatusChanged", "work_item", "wi1", {"status": "running"}),
    ("WorkItemStatusChanged", "work_item", "wi1", {"status": "completed"}),
    ("WorkItemDeleted", "work_item", "wi1", {}),
    # Conversations
    ("ConversationCreated", "conversation", "conv1", {"title": "Rebuild chat"}),
    (
        "MessageAppended",
        "conversation",
        "conv1",
        {
            "message_id": "msg1",
            "role": "user",
            "content": "Hello rebuild",
            "tool_calls": None,
            "tool_call_id": None,
        },
    ),
    # Notifications
    (
        "NotificationCreated",
        "notification",
        "n1",
        {
            "type": "review",
            "title": "Daily review",
            "content": "Summary text",
            "created_at": "2026-06-10T00:00:00Z",
        },
    ),
    ("NotificationRead", "notification", "n1", {}),
    # Policy
    ("PolicyCreated", "policy", "policy_read_file", {"capability": "read_file", "risk_level": "low"}),
    ("PolicyCreated", "policy", "policy_shell_exec", {"capability": "shell_exec", "risk_level": "high"}),
    ("PolicyCreated", "policy", "policy_forbidden_tool", {"capability": "forbidden_tool", "risk_level": "forbidden"}),
    # Timer
    ("TimerCreated", "timer", "timer_cron_1", {"handler_name": "test_timer", "schedule_type": "cron", "cron_expr": "hour=8,minute=0", "fire_at": "2026-06-10T08:00:00Z"}),
    ("TimerFired", "timer", "timer_cron_1", {"fired_at": "2026-06-10T08:00:00Z"}),
]


def snapshot(db: Any, tables: list[str]) -> dict:
    with db.get_db() as conn:
        return {
            t: [dict(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid").fetchall()]
            for t in tables
        }


def main() -> int:
    tables = [
        "work_items", "approvals", "memories", "conversations",
        "messages", "notifications", "timer_events", "policy_events",
    ]
    failed = False

    with ephemeral_kernel("verify_rebuild.db") as (db, k):
        for evt in SAMPLE_SCENARIO:
            k.emit_event(*evt[:3], payload=evt[3] if len(evt) > 3 else {}, actor="verify")

        before = snapshot(db, tables)

        result = k.rebuild_all()
        for at in sorted(result):
            print(f"  rebuild({at!r}): {result[at]} events")

        after = snapshot(db, tables)

        for t in tables:
            if before.get(t) != after.get(t):
                print(f"FAIL: {t!r} projection differs after rebuild", file=sys.stderr)
                print(f"  before: {len(before.get(t, []))} rows", file=sys.stderr)
                print(f"  after:  {len(after.get(t, []))} rows", file=sys.stderr)
                failed = True

    if failed:
        print("REBUILD VERIFICATION FAILED — Event Log cannot reconstruct State", file=sys.stderr)
        return 1

    print("REBUILD VERIFICATION PASSED — all projections byte-identical after rebuild")
    return 0


if __name__ == "__main__":
    sys.exit(main())
