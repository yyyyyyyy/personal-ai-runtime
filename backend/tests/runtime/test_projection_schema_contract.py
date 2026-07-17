"""Schema contract tests — governed projections must match expected columns."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.store.database import Database
from app.store.table_registry import (
    ALL_CLASSIFIED_TABLES,
    APP_STORAGE_SCHEMA,
    APP_STORAGE_TABLES,
    GOVERNED_SCHEMA,
    GOVERNED_TABLES,
)


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _assert_schema_contract(conn, schema: dict[str, frozenset[str]]) -> None:
    for table, expected_cols in schema.items():
        actual = _table_columns(conn, table)
        assert actual == set(expected_cols), (
            f"{table}: expected {sorted(expected_cols)}, got {sorted(actual)}"
        )


def test_governed_and_app_storage_disjoint():
    overlap = GOVERNED_TABLES & APP_STORAGE_TABLES
    assert not overlap, f"Tables in both sets: {overlap}"


def test_all_business_tables_classified(tmp_path):
    db = Database(db_path=str(tmp_path / "registry.db"))
    Kernel(db=db)

    with db.get_db() as conn:
        actual = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }

    unclassified = actual - ALL_CLASSIFIED_TABLES
    assert not unclassified, f"Unclassified tables: {unclassified}"


def test_projection_columns_match_contract(tmp_path):
    db = Database(db_path=str(tmp_path / "schema.db"))
    Kernel(db=db)

    with db.get_db() as conn:
        # Check governed projections
        _assert_schema_contract(conn, GOVERNED_SCHEMA)
        # Check app storage
        _assert_schema_contract(conn, APP_STORAGE_SCHEMA)


def test_projection_columns_match_contract_alembic_path(tmp_path, monkeypatch):
    """Alembic production path must satisfy the same column contract as raw DDL."""
    prod_path = str(tmp_path / "prod_schema.db")
    monkeypatch.setattr("app.config.settings.sqlite_path", prod_path)
    monkeypatch.setattr("app.store.schema_init.settings.sqlite_path", prod_path)

    from app.store.schema_init import ensure_schema

    ensure_schema(Database(db_path=prod_path))

    with Database(db_path=prod_path).get_db() as conn:
        _assert_schema_contract(conn, GOVERNED_SCHEMA)
        _assert_schema_contract(conn, APP_STORAGE_SCHEMA)
