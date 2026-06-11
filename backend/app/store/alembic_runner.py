"""Alembic migration runner — called at application startup to ensure DB schema is current."""

import logging
import os
from pathlib import Path

from alembic.config import Config

from alembic import command

logger = logging.getLogger(__name__)

_ALEMBIC_INI = Path(__file__).resolve().parent.parent.parent / "alembic.ini"


def run_migrations() -> None:
    """Run all pending Alembic migrations (idempotent — safe to call every startup)."""
    if not _ALEMBIC_INI.is_file():
        logger.warning("alembic.ini not found at %s — skipping migrations", _ALEMBIC_INI)
        return

    os.environ.setdefault("LLM_API_KEY", "alembic-migration-key")

    alembic_cfg = Config(str(_ALEMBIC_INI))
    try:
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations applied successfully")
    except Exception as exc:
        logger.error("Alembic migration failed: %s", exc)
        raise
