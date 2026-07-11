"""Projectors — turn the immutable Event Log into mutable State (materialized views).

Per docs/RUNTIME_SPEC.md: State is a *projection* of Events, never written directly.
A projector consumes events and materializes a read model (here: the `goals` table).
Because the projection is fully derived, it can always be wiped and rebuilt by
replaying the Event Log — that is the core property this slice proves.
"""

from __future__ import annotations

from typing import Callable

from .event import Event

# A projector handler applies a single event to a projection, using an open
# sqlite connection provided by the Kernel (Kernel Space owns storage access).
Handler = Callable[[Event, "object"], None]

_HANDLERS: dict[str, Handler] = {}
# aggregate_type -> projection table(s) this projector owns (used by rebuild).
_OWNED_TABLES: dict[str, list[str]] = {}


def projector(*event_types: str):
    """Register a handler for one or more event types."""

    def deco(fn: Handler) -> Handler:
        for et in event_types:
            _HANDLERS[et] = fn
        return fn

    return deco


def apply(event: Event, conn) -> None:
    """Apply one event to its projection, if a projector handles it."""
    handler = _HANDLERS.get(event.type)
    if handler is not None:
        handler(event, conn)


def owned_tables(aggregate_type: str) -> list[str]:
    return _OWNED_TABLES.get(aggregate_type, [])


# Side-effect imports: each projectors_* module registers handlers via @projector.
# Kept here (not a separate projectors.py) so runtime_files stays zero-sum when
# other Kernel collaborators are extracted.
from . import (  # noqa: E402, F401
    projectors_chat,
    projectors_core,
    projectors_execution,
    projectors_governance,
    projectors_inbox,
)

