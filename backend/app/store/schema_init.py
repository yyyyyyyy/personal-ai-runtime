"""Shared schema initialization — Alembic for production DB, raw DDL for test/custom DBs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from app.store.database import Database

logger = logging.getLogger(__name__)


def uses_alembic(db_path: str) -> bool:
    """Return True when db_path is the configured production SQLite file."""
    return Path(db_path).resolve() == Path(settings.sqlite_path).resolve()


def apply_projection_ddl(db: Database) -> None:
    """Ensure projection tables exist (idempotent).

    These tables are owned by Kernel projectors but are not in the Alembic
    baseline; production DBs need this after ``run_migrations()``.
    """
    from app.core.runtime.kernel.projectors_governance import GRANT_DDL, POLICY_DDL
    from app.core.runtime.kernel.projectors_timer import TIMER_DDL

    with db.get_db() as conn:
        conn.executescript(TIMER_DDL)
        conn.executescript(POLICY_DDL)
        conn.executescript(GRANT_DDL)
        # Migration: add sources column to messages for "I Remember" persistence
        _migrate_messages_sources(conn)


def _migrate_messages_sources(conn) -> None:
    """Add sources column to messages table if it doesn't exist (Phase 1 migration)."""
    import sqlite3
    try:
        conn.execute("ALTER TABLE messages ADD COLUMN sources TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists


def apply_raw_ddl(db: Database) -> None:
    """Apply inline DDL for test/custom databases (no Alembic)."""
    from app.core.runtime.kernel.kernel import (
        EVENT_LOG_SCHEMA,
        HANDLER_EXECUTIONS_SCHEMA,
        MEMORIES_LEGACY_DDL,
        PROJECTION_CHECKPOINTS_SCHEMA,
    )
    from app.store.schema_ddl import APP_STORAGE_DDL

    with db.get_db() as conn:
        conn.executescript(APP_STORAGE_DDL)
        conn.executescript(EVENT_LOG_SCHEMA)
        conn.executescript(PROJECTION_CHECKPOINTS_SCHEMA)
        conn.executescript(HANDLER_EXECUTIONS_SCHEMA)
        for stmt in MEMORIES_LEGACY_DDL:
            try:
                conn.execute(stmt)
            except Exception:
                logger.warning("Legacy DDL statement failed (may be expected): %s", stmt[:80])
    apply_projection_ddl(db)


def ensure_schema(db: Database) -> None:
    """Initialize schema: Alembic on production path, raw DDL elsewhere."""
    if not uses_alembic(db.db_path):
        apply_raw_ddl(db)
        return

    try:
        from app.store.alembic_runner import run_migrations

        run_migrations()
        apply_projection_ddl(db)
    except Exception as exc:
        logger.warning("Alembic migrations unavailable, using raw DDL: %s", exc)
        apply_raw_ddl(db)
