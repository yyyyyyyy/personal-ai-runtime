"""Tests for schema initialization."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.store.database import Database
from app.store.schema_init import apply_projection_ddl, ensure_schema, uses_alembic


def test_uses_alembic_matches_settings_path(tmp_path, monkeypatch):
    prod_path = str(tmp_path / "prod.db")
    monkeypatch.setattr("app.config.settings.sqlite_path", prod_path)
    monkeypatch.setattr("app.store.schema_init.settings.sqlite_path", prod_path)
    assert uses_alembic(prod_path) is True
    assert uses_alembic(str(tmp_path / "custom.db")) is False


def test_apply_raw_ddl_creates_core_tables(tmp_path):
    db = Database(db_path=str(tmp_path / "raw.db"))
    with db.get_db() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "work_items" in tables
    assert "event_log" in tables


def test_ensure_schema_on_custom_db(tmp_path):
    db_path = str(tmp_path / "ensure.db")
    db = Database(db_path=db_path)
    k = Kernel(db=db)
    k.emit_event("WorkItemCreated", "work_item", "g1", payload={'work_type': 'goal', "title": "Test"})
    rows = k.query_state("goals", id="g1")
    assert rows and rows[0]["title"] == "Test"


def test_ensure_schema_idempotent(tmp_path):
    db_path = str(tmp_path / "idem.db")
    ensure_schema(Database(db_path=db_path))
    ensure_schema(Database(db_path=db_path))
    with Database(db_path=db_path).get_db() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM work_items WHERE work_type = 'goal'"
        ).fetchone()[0] == 0


def test_apply_projection_ddl_creates_timer_and_governance_tables(tmp_path):
    db_path = str(tmp_path / "proj.db")
    db = Database(db_path=db_path)
    apply_projection_ddl(db)
    with db.get_db() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"timer_events", "policy_events"} <= tables


def test_ensure_schema_alembic_path_includes_projection_tables(tmp_path, monkeypatch):
    """Production DB (Alembic path) must get projector-owned tables after migrations."""
    prod_path = str(tmp_path / "prod.db")
    monkeypatch.setattr("app.config.settings.sqlite_path", prod_path)
    monkeypatch.setattr("app.store.schema_init.settings.sqlite_path", prod_path)

    ensure_schema(Database(db_path=prod_path))

    with Database(db_path=prod_path).get_db() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "work_items" in tables
    assert {"timer_events", "policy_events"} <= tables
