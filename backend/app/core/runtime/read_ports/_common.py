"""Shared Kernel / DB accessors for read ports."""

from __future__ import annotations

import logging

logger = logging.getLogger("app.core.runtime.read_ports")


def kernel():
    """Resolve Kernel at call time (supports test patches / RuntimeContainer.reset)."""
    from app.core.runtime.kernel_instance import kernel as k
    return k


def qb():
    from app.core.runtime.kernel import query_builder as qb_mod
    return qb_mod


def db():
    return kernel()._db
