#!/usr/bin/env python
"""Verify lossless export → import roundtrip for Event Log + chat data."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.agents.conversation import ConversationAPI, ConversationManager
from app.core.runtime.kernel import Kernel
from app.core.runtime.kernel.kernel_sovereignty import EXPORT_FORMAT
from app.store.database import Database


def main() -> int:
    source_path = _BACKEND_ROOT / "data" / "verify_export_roundtrip.db"
    import_path = _BACKEND_ROOT / "data" / "verify_export_roundtrip_import.db"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    for p in (source_path, import_path):
        if p.exists():
            p.unlink()

    source_db = Database(db_path=str(source_path))
    source_kernel = Kernel(db=source_db)

    source_kernel.emit_event(
        "GoalCreated",
        "goal",
        "g-export-1",
        payload={"title": "Export test goal", "importance": 0.8},
        actor="verify",
    )
    source_kernel.emit_event(
        "MemoryDerived",
        "memory",
        "m-export-1",
        payload={"category": "fact", "content": "Roundtrip memory", "confidence": 0.7},
        actor="verify",
    )

    conv = ConversationAPI.create(title="Roundtrip chat", kernel=source_kernel)
    mgr = ConversationManager(conv["id"], kernel=source_kernel)
    mgr.save_user_message("Hello export")
    mgr.save_assistant_message("Hello import")

    source_kernel.emit_event(
        "NotificationCreated",
        "notification",
        "n-export-1",
        payload={
            "type": "alert",
            "title": "Export test",
            "content": "Roundtrip notification",
            "created_at": "2026-06-10T00:00:00Z",
        },
        actor="verify",
    )

    snapshot = source_kernel.snapshot()
    if snapshot["format"] != EXPORT_FORMAT:
        print(f"FAIL: expected format {EXPORT_FORMAT}", file=sys.stderr)
        return 1
    if len(snapshot["event_log"]) < 2:
        print("FAIL: event_log too short", file=sys.stderr)
        return 1

    before = source_kernel.table_counts(("event_log","conversations","messages","goals","memories","notifications"))

    import_db = Database(db_path=str(import_path))
    import_kernel = Kernel(db=import_db)

    result = import_kernel.restore(snapshot, read_only=False)
    after = import_kernel.table_counts(("event_log","conversations","messages","goals","memories","notifications"))

    failed = False
    for key in ("event_log", "conversations", "messages", "goals", "memories", "notifications"):
        if before.get(key) != after.get(key):
            print(
                f"FAIL: count mismatch for {key!r}: before={before.get(key)} after={after.get(key)}",
                file=sys.stderr,
            )
            failed = True

    goals = import_kernel.query_state("goals", id="g-export-1")
    if not goals or goals[0].get("title") != "Export test goal":
        print("FAIL: goal projection not restored", file=sys.stderr)
        failed = True

    msgs = import_db.get_recent_messages(conv["id"], limit=10)
    if len(msgs) != 2 or msgs[0]["content"] != "Hello export":
        print("FAIL: messages not restored", file=sys.stderr)
        failed = True

    notifs = import_kernel.query_state("notifications", id="n-export-1")
    if not notifs or notifs[0].get("title") != "Export test":
        print("FAIL: notification projection not restored", file=sys.stderr)
        failed = True

    print(json.dumps({"import_result": result, "before": before, "after": after}, indent=2))

    for p in (source_path, import_path):
        try:
            p.unlink(missing_ok=True)
        except PermissionError:
            pass

    if failed:
        print("EXPORT ROUNDTRIP FAILED", file=sys.stderr)
        return 1

    print("EXPORT ROUNDTRIP PASSED — lossless event_log + chat restore")
    return 0


if __name__ == "__main__":
    sys.exit(main())
