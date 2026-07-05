#!/usr/bin/env python
"""Rebuild verification guard: replay the Event Log and verify projections.

This script emits a set of sample events, snapshots the projection tables,
performs a full rebuild, then asserts the post-rebuild state is identical.
Non-zero exit means the Event Log cannot reconstruct State — a Runtime invariant
violation that must block CI.
"""

import os
import sys
from pathlib import Path

# Running as `python scripts/verify_rebuild.py` puts scripts/ on sys.path, not backend/.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")

from typing import Any

from app.core.runtime.kernel import Kernel
from app.store.database import Database

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
    # WorkItem (v0.5.0: unified task + action)
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
    # Policy (Phase 3)
    ("PolicyCreated", "policy", "policy_read_file", {"capability": "read_file", "risk_level": "low"}),
    ("PolicyCreated", "policy", "policy_shell_exec", {"capability": "shell_exec", "risk_level": "high"}),
    ("PolicyCreated", "policy", "policy_forbidden_tool", {"capability": "forbidden_tool", "risk_level": "forbidden"}),
    # Timer (Phase 2)
    ("TimerCreated", "timer", "timer_cron_1", {"handler_name": "test_timer", "schedule_type": "cron", "cron_expr": "hour=8,minute=0", "fire_at": "2026-06-10T08:00:00Z"}),
    ("TimerFired", "timer", "timer_cron_1", {"fired_at": "2026-06-10T08:00:00Z"}),
]


def snapshot(db: Database, tables: list[str]) -> dict:
    with db.get_db() as conn:
        return {
            t: [dict(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid").fetchall()]
            for t in tables
        }


def main():
    db_path = Path(__file__).resolve().parent.parent / "data" / "verify_rebuild.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path=str(db_path))
    k = Kernel(db=db)

    tables = ["work_items", "approvals", "memories", "conversations", "messages", "notifications", "timer_events", "policy_events"]

    # 1. Emit sample scenario
    for evt in SAMPLE_SCENARIO:
        k.emit_event(*evt[:3], payload=evt[3] if len(evt) > 3 else {}, actor="verify")

    before = snapshot(db, tables)

    # 2. Rebuild all registered aggregate types
    result = k.rebuild_all()
    for at in sorted(result):
        print(f"  rebuild({at!r}): {result[at]} events")

    after = snapshot(db, tables)

    # 3. Assert identity
    failed = False
    for t in tables:
        if before.get(t) != after.get(t):
            print(f"FAIL: {t!r} projection differs after rebuild", file=sys.stderr)
            print(f"  before: {len(before.get(t, []))} rows", file=sys.stderr)
            print(f"  after:  {len(after.get(t, []))} rows", file=sys.stderr)
            failed = True

    # Cleanup (best-effort; may fail on Windows due to WAL locks)
    try:
        db_path.unlink(missing_ok=True)
    except PermissionError:
        pass

    if failed:
        print("REBUILD VERIFICATION FAILED — Event Log cannot reconstruct State", file=sys.stderr)
        sys.exit(1)

    print("REBUILD VERIFICATION PASSED — all projections byte-identical after rebuild")


if __name__ == "__main__":
    main()
