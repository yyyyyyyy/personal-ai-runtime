"""Alembic schema runner — called at application startup to initialize the DB schema."""

import logging
import os
from pathlib import Path

from alembic.config import Config

from alembic import command

logger = logging.getLogger(__name__)

_ALEMBIC_INI = Path(__file__).resolve().parent.parent.parent / "alembic.ini"


def run_migrations() -> None:
    """Apply the Alembic schema to head (idempotent — safe to call every startup)."""
    if not _ALEMBIC_INI.is_file():
        logger.warning("alembic.ini not found at %s — skipping schema setup", _ALEMBIC_INI)
        return

    os.environ.setdefault("LLM_API_KEY", "alembic-migration-key")

    alembic_cfg = Config(str(_ALEMBIC_INI))
    try:
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic schema applied successfully")
    except Exception as exc:
        logger.error("Alembic schema setup failed: %s", exc)
        raise
