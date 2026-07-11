"""Typed query-construction helpers for Kernel read paths.

Centralises the patterns that were previously hand-written across the Kernel
mixins (``WHERE`` clause assembly, ``LIMIT``/``ORDER BY`` injection,
``IN (...)`` placeholders). Goals:

- No ad-hoc f-strings in call sites — every fragment is built here.
- ``int(limit)`` coercion lives in exactly one place, with a sane ceiling.
- ``ORDER BY`` clauses are validated against an allowlist dict so callers
  cannot inject arbitrary SQL via the ``order`` parameter — unknown keys
  fall back to the default rather than being interpolated.

This module emits only SQLite fragments; it never opens a connection.
``check_boundary.py`` treats ``core/runtime/kernel`` as Kernel Space, so
introducing SQL here does not violate the governance boundary.
"""

from __future__ import annotations

from typing import Any, Iterable

# A defensive upper bound — none of the current call sites need more than a
# few hundred rows. Keeps a runaway ``limit`` from dragging the DB.
MAX_LIMIT = 5000


def safe_limit(limit: int | None, default: int | None = None) -> str:
    """Return a ``LIMIT ?``-free SQL fragment with the integer already inlined.

    All limits flow through here so we can guarantee (a) the value is an int
    and (b) it never exceeds :data:`MAX_LIMIT`. Returns ``""`` when neither
    ``limit`` nor ``default`` is supplied.
    """
    if limit is None:
        if default is None:
            return ""
        limit = default
    n = int(limit)
    if n < 0:
        n = 0
    if n > MAX_LIMIT:
        n = MAX_LIMIT
    return f" LIMIT {n}"


def safe_offset(offset: int | None) -> str:
    """Return an ``OFFSET N`` fragment, or ``""`` when unset/zero."""
    if not offset:
        return ""
    n = int(offset)
    if n < 0:
        n = 0
    if n > MAX_LIMIT * 10:
        n = MAX_LIMIT * 10
    return f" OFFSET {n}"


def safe_order(order: str | None, allowed: dict[str, str], default_key: str) -> str:
    """Return an ``ORDER BY`` fragment validated against ``allowed``.

    ``allowed`` maps a stable public name (e.g. ``"importance_desc"``) to a
    literal SQL fragment. Unknown keys fall back to ``allowed[default_key]``
    rather than being interpolated — this closes the order-by injection
    surface that previously existed wherever ``f"ORDER BY {order_sql}"`` was
    written.
    """
    if order is None:
        order = default_key
    return f" ORDER BY {allowed.get(order, allowed[default_key])}"


def in_clause(values: Iterable[Any]) -> tuple[str, list[Any]]:
    """Build an ``IN (?, ?, ...)`` placeholder list with matching params.

    Returns ``("", [])`` for an empty input so callers can compose it into a
    larger ``WHERE`` without special-casing.
    """
    seq = list(values)
    if not seq:
        return "", []
    placeholders = ",".join("?" * len(seq))
    return f"IN ({placeholders})", seq


def build_where(clauses: list[str]) -> str:
    """Join filter clauses into a ``WHERE ...`` fragment (empty when no clauses).

    Params are owned by the caller; this helper only assembles the clause
    text, so callers retain full control over parameter ordering.
    """
    if not clauses:
        return ""
    return " WHERE " + " AND ".join(clauses)
