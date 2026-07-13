"""User-profile read ports."""

from __future__ import annotations

from typing import Any

from app.core.runtime.read_ports._common import db, qb


def query_user_profile_category(category: str) -> dict[str, Any] | None:
    rows = qb().query_user_profile(db(), {"id": category, "limit": 1})
    return rows[0] if rows else None


def query_user_profile(*, limit: int = 50) -> list[dict[str, Any]]:
    return qb().query_user_profile(db(), {"limit": limit})

