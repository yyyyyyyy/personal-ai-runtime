"""Schema contract tests — governed projections must match expected columns."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.store.database import Database
from app.store.table_registry import (
    ALL_CLASSIFIED_TABLES,
    APP_STORAGE_TABLES,
    GOVERNED_SCHEMA,
    GOVERNED_TABLES,
)


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def test_governed_and_app_storage_disjoint():
    overlap = GOVERNED_TABLES & APP_STORAGE_TABLES
    assert not overlap, f"Tables in both sets: {overlap}"


def test_all_business_tables_classified(tmp_path):
    db = Database(db_path=str(tmp_path / "registry.db"))
    Kernel(db=db)  # ensures event_log + memory migrations

    with db.get_db() as conn:
        actual = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }

    unclassified = actual - ALL_CLASSIFIED_TABLES
    assert not unclassified, f"Unclassified tables: {unclassified}"


def test_governed_projection_columns_match_contract(tmp_path):
    db = Database(db_path=str(tmp_path / "schema.db"))
    Kernel(db=db)

    with db.get_db() as conn:
        for table, expected_cols in GOVERNED_SCHEMA.items():
            actual = _table_columns(conn, table)
            assert actual == set(expected_cols), (
                f"{table}: expected {sorted(expected_cols)}, got {sorted(actual)}"
            )
