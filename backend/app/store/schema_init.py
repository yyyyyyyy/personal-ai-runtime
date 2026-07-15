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
    """Ensure projector-owned projection tables exist (idempotent).

    These tables are owned by Kernel projectors; production DBs apply them
    after the Alembic baseline. All columns are part of the CREATE statements.
    """
    from app.core.runtime.kernel.projectors_governance import POLICY_DDL
    from app.core.runtime.kernel.projectors_inbox import TIMER_DDL
    from app.store.schema_ddl import MEMORY_INDEX_REPAIRS_SCHEMA

    with db.get_db() as conn:
        conn.executescript(TIMER_DDL)
        conn.executescript(POLICY_DDL)
        conn.executescript(MEMORY_INDEX_REPAIRS_SCHEMA)


def apply_raw_ddl(db: Database) -> None:
    """Apply inline DDL for test/custom databases (no Alembic)."""
    from app.store.schema_ddl import (
        APP_STORAGE_DDL,
        APP_STORAGE_DDL_TAIL,
        EVENT_LOG_SCHEMA,
        HANDLER_EXECUTIONS_SCHEMA,
        MEMORY_INDEX_REPAIRS_SCHEMA,
        POLICY_EVENTS_SCHEMA,
        PROJECTION_CHECKPOINTS_SCHEMA,
        TIMER_EVENTS_SCHEMA,
        WORK_ITEMS_SCHEMA,
    )

    with db.get_db() as conn:
        conn.executescript(APP_STORAGE_DDL)
        conn.executescript(WORK_ITEMS_SCHEMA)
        conn.executescript(APP_STORAGE_DDL_TAIL)
        conn.executescript(EVENT_LOG_SCHEMA)
        conn.executescript(PROJECTION_CHECKPOINTS_SCHEMA)
        conn.executescript(HANDLER_EXECUTIONS_SCHEMA)
        conn.executescript(TIMER_EVENTS_SCHEMA)
        conn.executescript(POLICY_EVENTS_SCHEMA)
        conn.executescript(MEMORY_INDEX_REPAIRS_SCHEMA)


def ensure_schema(db: Database) -> None:
    """Initialize schema: Alembic on production path, raw DDL elsewhere."""
    if not uses_alembic(db.db_path):
        apply_raw_ddl(db)
        return

    from app.store.alembic_runner import run_migrations
    try:
        run_migrations()
    except Exception as exc:
        logger.warning("Alembic unavailable, using raw DDL: %s", exc)
        apply_raw_ddl(db)
        return

    # Projector-owned tables are not declared in Alembic; ensure they exist.
    apply_projection_ddl(db)

    from app.store.schema_ddl import WORK_ITEMS_SCHEMA
    with db.get_db() as conn:
        conn.executescript(WORK_ITEMS_SCHEMA)
