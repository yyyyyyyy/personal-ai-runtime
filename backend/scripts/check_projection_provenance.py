#!/usr/bin/env python
"""Projection provenance guard — join-based traceability to event_log (Strategy A).

Verifies that rows in goals, approvals, and handler_executions can be traced
to the Event Log without schema changes or projector edits:

  - goals / approvals: at least one event_log row for (aggregate_type, aggregate_id)
  - handler_executions: ExecutionRequested exists for the row id; when event_id is
    non-empty, (event_id, event_seq) must match an event_log row (trigger event)

Philosophy: INV-P7 is enforced by CI join checks, not by source_event_* columns.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, TextIO

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel.constants import (  # noqa: E402
    AGGREGATE_APPROVAL,
    AGGREGATE_CONVERSATION,
    AGGREGATE_EXECUTION,
    AGGREGATE_INBOX_EMAIL,
    AGGREGATE_MEMORY,
    AGGREGATE_WORK_ITEM,
    EVENT_EXECUTION_REQUESTED,
    EVENT_INBOX_EMAIL_RECORDED,
)

Violation = tuple[str, str, str]  # (table, row_id, reason)


def check_provenance(conn: Any) -> list[Violation]:
    """Return provenance violations for approvals, handler_executions."""
    violations: list[Violation] = []

    for row in conn.execute("SELECT id FROM approvals").fetchall():
        approval_id = row["id"]
        found = conn.execute(
            """SELECT 1 FROM event_log
               WHERE aggregate_type = ? AND aggregate_id = ?
               LIMIT 1""",
            (AGGREGATE_APPROVAL, approval_id),
        ).fetchone()
        if not found:
            violations.append(
                (
                    "approvals",
                    approval_id,
                    f"no event_log row for aggregate_type={AGGREGATE_APPROVAL!r}",
                ),
            )

    for row in conn.execute(
        "SELECT id, event_id, event_seq FROM handler_executions"
    ).fetchall():
        execution_id = row["id"]
        found = conn.execute(
            """SELECT 1 FROM event_log
               WHERE aggregate_type = ? AND aggregate_id = ? AND type = ?
               LIMIT 1""",
            (AGGREGATE_EXECUTION, execution_id, EVENT_EXECUTION_REQUESTED),
        ).fetchone()
        if not found:
            violations.append(
                (
                    "handler_executions",
                    execution_id,
                    f"no {EVENT_EXECUTION_REQUESTED!r} in event_log",
                ),
            )

        trigger_id = row["event_id"] or ""
        if trigger_id:
            trigger_seq = int(row["event_seq"])
            trigger_found = conn.execute(
                "SELECT 1 FROM event_log WHERE id = ? AND seq = ? LIMIT 1",
                (trigger_id, trigger_seq),
            ).fetchone()
            if not trigger_found:
                violations.append(
                    (
                        "handler_executions",
                        execution_id,
                        f"trigger event ({trigger_id!r}, seq={trigger_seq}) not in event_log",
                    ),
                )

    for row in conn.execute(
        "SELECT id, conversation_id, source_event_id FROM messages"
    ).fetchall():
        msg_id = row["id"]
        source_event_id = row["source_event_id"] or ""

        if not source_event_id:
            violations.append(
                ("messages", msg_id, "source_event_id is null or empty"),
            )
            continue

        found = conn.execute(
            "SELECT 1 FROM event_log WHERE id = ? LIMIT 1",
            (source_event_id,),
        ).fetchone()
        if not found:
            violations.append(
                (
                    "messages",
                    msg_id,
                    f"source_event_id {source_event_id!r} not in event_log",
                ),
            )

        conv_id = row["conversation_id"] or ""
        if conv_id:
            conv_found = conn.execute(
                """SELECT 1 FROM event_log
                   WHERE aggregate_type = ? AND aggregate_id = ?
                   LIMIT 1""",
                (AGGREGATE_CONVERSATION, conv_id),
            ).fetchone()
            if not conv_found:
                violations.append(
                    (
                        "messages",
                        msg_id,
                        f"conversation_id {conv_id!r} has no event_log row",
                    ),
                )

    for row in conn.execute("SELECT id FROM conversations").fetchall():
        conv_id = row["id"]
        found = conn.execute(
            """SELECT 1 FROM event_log
               WHERE aggregate_type = ? AND aggregate_id = ?
               LIMIT 1""",
            (AGGREGATE_CONVERSATION, conv_id),
        ).fetchone()
        if not found:
            violations.append(
                (
                    "conversations",
                    conv_id,
                    f"no event_log row for aggregate_type={AGGREGATE_CONVERSATION!r}",
                ),
            )

    for row in conn.execute("SELECT id, parent_goal_id as goal_id FROM work_items WHERE work_type = 'action'").fetchall():
        action_id = row["id"]
        goal_id = row["goal_id"] or ""
        found = conn.execute(
            """SELECT 1 FROM event_log
               WHERE aggregate_type = ? AND aggregate_id = ?
               LIMIT 1""",
            (AGGREGATE_WORK_ITEM, action_id),
        ).fetchone()
        if not found:
            violations.append(
                ("work_items", action_id,
                 f"no event_log row for aggregate_type={'work_item'!r}"),
            )
        if goal_id:
            gf = conn.execute(
                """SELECT 1 FROM event_log
                   WHERE aggregate_type = ? AND aggregate_id = ?
                   LIMIT 1""",
                (AGGREGATE_WORK_ITEM, goal_id),
            ).fetchone()
            if not gf:
                violations.append(
                    ("work_items", action_id,
                     f"referenced goal_id {goal_id!r} has no event_log row"),
                )

    for row in conn.execute("SELECT id FROM memories").fetchall():
        mem_id = row["id"]
        found = conn.execute(
            """SELECT 1 FROM event_log
               WHERE aggregate_type = ? AND aggregate_id = ?
               LIMIT 1""",
            (AGGREGATE_MEMORY, mem_id),
        ).fetchone()
        if not found:
            violations.append(
                ("memories", mem_id,
                 f"no event_log row for aggregate_type={AGGREGATE_MEMORY!r}"),
            )

    # inbox_emails provenance — every row must trace to an
    # InboxEmailRecorded event (governed projection from projectors_inbox.py).
    for row in conn.execute("SELECT id FROM inbox_emails").fetchall():
        inbox_id = row["id"]
        found = conn.execute(
            """SELECT 1 FROM event_log
               WHERE aggregate_type = ? AND aggregate_id = ? AND type = ?
               LIMIT 1""",
            (AGGREGATE_INBOX_EMAIL, inbox_id, EVENT_INBOX_EMAIL_RECORDED),
        ).fetchone()
        if not found:
            violations.append(
                ("inbox_emails", inbox_id,
                 f"no {EVENT_INBOX_EMAIL_RECORDED!r} event in event_log"),
            )

    return violations


def print_violations(violations: list[Violation], stream: TextIO = sys.stderr) -> None:
    if not violations:
        return
    print("PROJECTION PROVENANCE VIOLATION — orphan or untraceable projection row:", file=stream)
    for table, row_id, reason in violations:
        print(f"  {table}:{row_id}  [{reason}]", file=stream)


def bootstrap_sample_scenario(kernel: Any) -> None:
    """Emit a minimal event chain so provenance checks pass on a fresh database."""
    trigger = kernel.emit_event(
        "WorkItemCreated",
        "work_item",
        "prov_task_1",
        payload={"title": "provenance sample", "work_type": "task"},
        actor="verify",
    )
    assert trigger.seq is not None

    kernel.emit_event(
        "WorkItemCreated",
        AGGREGATE_WORK_ITEM,
        "prov_goal_1",
        payload={"title": "Provenance sample goal", "work_type": "goal"},
        actor="verify",
    )
    kernel.emit_event(
        "WorkItemCreated",
        AGGREGATE_WORK_ITEM,
        "prov_goal_child",
        payload={"title": "Child goal", "work_type": "goal", "parent_work_id": "prov_goal_1"},
        actor="verify",
    )
    kernel.emit_event(
        "ApprovalRequested",
        AGGREGATE_APPROVAL,
        "prov_apr_1",
        payload={"action": "read_file", "ctx": {"args": {}}},
        actor="verify",
    )
    # Goal action provenance
    kernel.emit_event(
        "WorkItemCreated",
        "work_item",
        "prov_act_1",
        payload={"parent_goal_id": "prov_goal_1", "title": "Provenance action", "status": "pending", "work_type": "action"},
        actor="verify",
    )
    # Memory provenance
    kernel.emit_event(
        "MemoryDerived",
        AGGREGATE_MEMORY,
        "prov_mem_1",
        payload={"category": "fact", "content": "Provenance memory", "confidence": 0.8},
        actor="verify",
    )
    # inbox_emails provenance
    kernel.emit_event(
        EVENT_INBOX_EMAIL_RECORDED,
        AGGREGATE_INBOX_EMAIL,
        "prov_inbox_1",
        payload={"sender": "verify@example.com", "subject": "Provenance inbox",
                 "category": "actionable", "importance": 0.5},
        actor="verify",
    )

    execution_id = "prov_exec_1"
    kernel.emit_event(
        EVENT_EXECUTION_REQUESTED,
        AGGREGATE_EXECUTION,
        execution_id,
        payload={
            "execution_id": execution_id,
            "actor": "scheduler",
            "handler_name": "on_sample",
            "trigger_event_id": trigger.id,
            "trigger_event_seq": trigger.seq,
            "trigger_event_type": trigger.type,
            "instance_id": "inst_sample",
            "policy": {"timeout": 30.0, "max_retries": 3, "retry_delay": 5.0},
            "correlation_id": "corr_prov",
            "created_at": trigger.ts,
            "event_seq": trigger.seq,
        },
        actor="scheduler",
        caused_by=trigger.id,
    )

    # Conversation + message provenance
    conv = kernel.emit_event(
        "ConversationCreated",
        AGGREGATE_CONVERSATION,
        "prov_conv_1",
        payload={"title": "Provenance sample conversation"},
        actor="verify",
    )
    msg = kernel.emit_event(
        "MessageAppended",
        AGGREGATE_CONVERSATION,
        "prov_conv_1",
        payload={
            "message_id": "prov_msg_1",
            "role": "user",
            "content": "Hello from provenance test",
            "created_at": conv.ts,
        },
        actor="verify",
        caused_by=conv.id,
    )
    kernel.emit_event(
        "ConversationRecorded",
        AGGREGATE_CONVERSATION,
        "prov_conv_1",
        payload={
            "user_message": "Hello from provenance test",
            "assistant_message": "Response",
            "preview": "User: Hello from provenanc... Assistant: Response",
        },
        actor="verify",
        caused_by=msg.id,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Projection provenance guard for Personal AI Runtime",
    )
    parser.add_argument(
        "--db",
        type=Path,
        help="SQLite database path to check (default: bootstrap temp scenario)",
    )
    args = parser.parse_args(argv)

    if args.db is not None:
        from app.store.database import Database

        db = Database(db_path=str(args.db))
        with db.get_db() as conn:
            violations = check_provenance(conn)
    else:
        from app.core.runtime.kernel import Kernel
        from app.store.database import Database

        db_path = _BACKEND_ROOT / "data" / "verify_provenance.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass
        db = Database(db_path=str(db_path))
        kernel = Kernel(db=db)
        bootstrap_sample_scenario(kernel)
        with db.get_db() as conn:
            violations = check_provenance(conn)
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass

    if violations:
        print_violations(violations)
        return 1

    print(
        "PROJECTION PROVENANCE OK — work_items, approvals, handler_executions, "
        "conversations, messages, memories, inbox_emails traceable to event_log"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
