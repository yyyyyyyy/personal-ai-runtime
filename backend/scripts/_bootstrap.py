"""Shared bootstrap helpers for backend verification / guard scripts.

Canonical import (requires ``backend/`` on ``sys.path``, e.g. ``python -m``)::

    from scripts._bootstrap import BACKEND_ROOT, ephemeral_kernel, prepare_script_env

    with ephemeral_kernel("verify_example.db") as (db, kernel):
        ...
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPTS_DIR.parent


def ensure_backend_path() -> Path:
    """Put ``backend/`` on ``sys.path`` so ``import app...`` works."""
    root = str(BACKEND_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    return BACKEND_ROOT


def ensure_test_llm_key(value: str = "test-key") -> None:
    os.environ.setdefault("LLM_API_KEY", value)


def prepare_script_env(llm_key: str = "test-key") -> Path:
    """Ensure import path + test LLM key; return backend root."""
    ensure_backend_path()
    ensure_test_llm_key(llm_key)
    return BACKEND_ROOT


def _unlink_best_effort(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        pass


def _close_best_effort(db: Any) -> None:
    close = getattr(db, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


@contextmanager
def ephemeral_db_path(db_name: str, *, prepare: bool = True) -> Iterator[Path]:
    """Yield a clean ``data/<db_name>`` path and best-effort delete afterward.

    Set *prepare* to False when the caller already ran ``prepare_script_env``.
    """
    if prepare:
        prepare_script_env()
    db_path = BACKEND_ROOT / "data" / db_name
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _unlink_best_effort(db_path)
    try:
        yield db_path
    finally:
        _unlink_best_effort(db_path)


@contextmanager
def ephemeral_kernel(
    db_name: str,
    *,
    install_singleton: bool = False,
    memory_index: Any = None,
) -> Iterator[tuple[Any, Any]]:
    """Create a fresh ``Database`` + ``Kernel``, yield ``(db, kernel)``, then clean up.

    When *install_singleton* is True, temporarily assign the instance to
    ``app.core.runtime.kernel_instance.kernel`` and restore the previous
    value on exit.
    """
    prepare_script_env()
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    with ephemeral_db_path(db_name, prepare=False) as db_path:
        db = Database(db_path=str(db_path))
        kernel = (
            Kernel(db=db, memory_index=memory_index)
            if memory_index is not None
            else Kernel(db=db)
        )
        prev_kernel: Any = None
        ki: Any = None
        if install_singleton:
            import app.core.runtime.kernel_instance as ki

            prev_kernel = ki.kernel
            ki.kernel = kernel  # type: ignore[assignment]
        try:
            yield db, kernel
        finally:
            if install_singleton and ki is not None:
                try:
                    ki.kernel = prev_kernel
                except Exception:
                    pass
            _close_best_effort(db)
