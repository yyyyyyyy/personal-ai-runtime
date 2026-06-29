"""Current Execution scope — ContextVar binding for invoke_capability (D2)."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator

_current_execution_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_execution_id",
    default=None,
)

RUNTIME_OWNERSHIP_ACTORS = frozenset({"scheduler", "executor", "background"})


def get_current_execution_id() -> str | None:
    return _current_execution_id.get()


def actor_requires_execution_ownership(actor: str) -> bool:
    if actor.startswith("agent:"):
        return True
    return actor in RUNTIME_OWNERSHIP_ACTORS


@contextmanager
def execution_scope(execution_id: str) -> Iterator[None]:
    token = _current_execution_id.set(execution_id)
    try:
        yield
    finally:
        _current_execution_id.reset(token)
