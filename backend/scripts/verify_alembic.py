#!/usr/bin/env python
"""Database schema verification — required tables and FK settings.

Mirrors the CI schema check in .github/workflows/ci.yml.
Non-zero exit means the local SQLite schema is incomplete or misconfigured.
"""

import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")

REQUIRED_TABLES = [
    "conversations",
    "messages",
    "goals",
    "actions",
    "events",
    "memories",
    "notifications",
    "schedules",
    "activity_log",
    "tasks",
    "llm_calls",
    "tool_calls",
    "approvals",
    "background_tasks",
    "triggers",
    "user_profile",
    "inbox_emails",
    "app_settings",
    "timer_events",
    "policy_events",
    "grant_events",
]


def main() -> int:
    from app.store.database import db

    with db.get_db() as conn:
        tables = {
            row["name"]
            for row in conn.execute(
                'SELECT name FROM sqlite_master WHERE type="table"'
            ).fetchall()
        }
        missing = [name for name in REQUIRED_TABLES if name not in tables]
        if missing:
            print(f"FAIL: missing tables: {missing}", file=sys.stderr)
            return 1

        fk_on = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        if fk_on != 1:
            print("FAIL: foreign keys are OFF", file=sys.stderr)
            return 1

    print(f"OK: {len(REQUIRED_TABLES)} tables, FK=ON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
