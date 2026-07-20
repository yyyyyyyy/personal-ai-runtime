#!/usr/bin/env python
"""Database schema verification — required tables and FK settings.

Uses an ephemeral SQLite DB so parallel CI jobs never touch the developer's
default ``personal_ai.db``. Table inventory is sourced from
``app.store.table_registry.ALL_CLASSIFIED_TABLES``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from scripts._bootstrap import ephemeral_db_path, prepare_script_env

prepare_script_env()

from app.store.table_registry import ALL_CLASSIFIED_TABLES  # noqa: E402

REQUIRED_TABLES = tuple(sorted(ALL_CLASSIFIED_TABLES))


def main() -> int:
    from app.store.database import Database

    with ephemeral_db_path("verify_alembic.db", prepare=False) as db_path:
        db = Database(db_path=str(db_path))
        try:
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
        finally:
            close = getattr(db, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    print(f"OK: {len(REQUIRED_TABLES)} tables, FK=ON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
