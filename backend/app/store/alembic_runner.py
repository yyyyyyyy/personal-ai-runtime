"""Alembic schema runner — called at application startup to initialize the DB schema."""

import logging
import os
from pathlib import Path
from typing import Optional

from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

logger = logging.getLogger(__name__)


def _find_alembic_ini() -> Path:
    """Locate alembic.ini with fallback strategies."""
    strategies = [
        # Strategy 1: Environment variable
        lambda: Path(os.environ.get("ALEMBIC_CONFIG", "")),
        # Strategy 2: Relative to this file (backend/app/store/alembic_runner.py)
        lambda: Path(__file__).resolve().parent.parent.parent / "alembic.ini",
        # Strategy 3: Current working directory
        lambda: Path.cwd() / "alembic.ini",
        # Strategy 4: Subdirectory 'backend' from CWD
        lambda: Path.cwd() / "backend" / "alembic.ini",
    ]

    for strategy in strategies:
        try:
            path = strategy()
            if path.is_file():
                return path
        except Exception:
            continue

    # Default fallback (might not exist, will be caught in run_migrations)
    return Path(__file__).resolve().parent.parent.parent / "alembic.ini"


_ALEMBIC_INI = _find_alembic_ini()


def run_migrations(db_url: Optional[str] = None) -> Optional[str]:
    """
    Apply the Alembic schema to head (idempotent — safe to call every startup).

    Args:
        db_url: Optional SQLAlchemy database URL to override default settings.

    Returns:
        The current head revision ID after migration.
    """
    if not _ALEMBIC_INI.is_file():
        logger.warning("alembic.ini not found at %s — skipping schema setup", _ALEMBIC_INI)
        return None

    # Guard: prevent some app models from crashing if they expect this key during import
    os.environ.setdefault("LLM_API_KEY", "alembic-migration-key")

    alembic_cfg = Config(str(_ALEMBIC_INI))
    if db_url:
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    try:
        command.upgrade(alembic_cfg, "head")

        # Log and return the current head for better observability
        script = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script.get_current_head()

        target = f" to {db_url}" if db_url else ""
        logger.info("Alembic schema applied successfully (head: %s)%s", head_rev, target)
        return head_rev
    except Exception as exc:
        logger.error("Alembic schema setup failed on %s: %s", _ALEMBIC_INI, exc)
        raise
