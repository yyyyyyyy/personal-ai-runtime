#!/usr/bin/env python
"""Conversation rebuild verification — validate source_event_id in messages.

Verifies that after Event Log rebuild:
1. Every message row has a non-empty source_event_id
2. Every source_event_id points to a valid event_log row
3. The conversation_id on each message has an event_log trace
"""

import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.store.database import Database

SAMPLE_EVENTS = [
    ("ConversationCreated", "conversation", "conv_rebuild_1",
     {"title": "Conversation Rebuild Test"}),
    ("MessageAppended", "conversation", "conv_rebuild_1",
     {"message_id": "msg_rebuild_user", "role": "user",
      "content": "User message in rebuild test"}),
    ("MessageAppended", "conversation", "conv_rebuild_1",
     {"message_id": "msg_rebuild_assistant", "role": "assistant",
      "content": "Assistant response in rebuild test"}),
]


def main():
    db_path = _BACKEND_ROOT / "data" / "verify_conv_rebuild.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        db_path.unlink(missing_ok=True)
    except PermissionError:
        pass

    db = Database(db_path=str(db_path))
    k = Kernel(db=db)

    for evt in SAMPLE_EVENTS:
        type_, agg_type, agg_id, payload = evt
        k.emit_event(type_, agg_type, agg_id, payload=payload, actor="verify")  # type: ignore[arg-type]

    k.rebuild_all()

    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id, conversation_id, source_event_id FROM messages ORDER BY id"
        ).fetchall()

        if len(rows) != 2:
            print(f"FAIL: expected 2 messages, got {len(rows)}", file=sys.stderr)
            sys.exit(1)

        for row in rows:
            msg_id = row["id"]
            source = row["source_event_id"]
            conv_id = row["conversation_id"]

            if not source:
                print(f"FAIL: message {msg_id} has empty source_event_id",
                      file=sys.stderr)
                sys.exit(1)

            found = conn.execute(
                "SELECT 1 FROM event_log WHERE id = ? LIMIT 1", (source,)
            ).fetchone()
            if not found:
                print(
                    f"FAIL: message {msg_id} source_event_id "
                    f"{source!r} not in event_log",
                    file=sys.stderr,
                )
                sys.exit(1)

            if conv_id != "conv_rebuild_1":
                print(f"FAIL: message {msg_id} unexpected conversation_id "
                      f"{conv_id!r}", file=sys.stderr)
                sys.exit(1)

    try:
        db_path.unlink(missing_ok=True)
    except PermissionError:
        pass

    print("CONVERSATION REBUILD VERIFICATION PASSED — "
          "messages traceable to event_log")
    return 0


if __name__ == "__main__":
    sys.exit(main())
