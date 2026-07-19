"""Approval projection read ports."""

from __future__ import annotations

import logging
from typing import Any

from app.core.runtime.read_ports._common import kernel

logger = logging.getLogger(__name__)


def query_pending_approval_count() -> int:
    """Count approvals currently waiting for user decision (exact COUNT)."""
    try:
        return kernel().count_state("approvals", status="pending")
    except Exception:
        logger.exception("query_pending_approval_count failed")
        raise


def query_pending_approvals(*, limit: int = 50) -> list[dict[str, Any]]:
    """List pending approvals (Work / Capability deferrals awaiting the user)."""
    return kernel().query_state("approvals", status="pending", limit=limit)


def query_approval(approval_id: str) -> dict[str, Any] | None:
    rows = kernel().query_state("approvals", id=approval_id, limit=1)
    return rows[0] if rows else None


def query_approvals(*, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {"limit": limit}
    if status:
        filters["status"] = status
    return kernel().query_state("approvals", **filters)
