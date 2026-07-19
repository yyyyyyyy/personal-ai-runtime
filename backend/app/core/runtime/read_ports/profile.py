"""User-profile read ports."""

from __future__ import annotations

from typing import Any

from app.core.runtime.read_ports._common import kernel


def query_user_profile_category(category: str) -> dict[str, Any] | None:
    rows = kernel().query_state("user_profile", id=category, limit=1)
    return rows[0] if rows else None


def query_user_profile(*, limit: int | None = None) -> list[dict[str, Any]]:
    """List profile categories. ``limit=None`` returns the full (small) table."""
    filters: dict[str, Any] = {}
    if limit is not None:
        filters["limit"] = limit
    return kernel().query_state("user_profile", **filters)
