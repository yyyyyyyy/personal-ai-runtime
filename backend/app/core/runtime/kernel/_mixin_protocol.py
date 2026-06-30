"""Protocol defining the Kernel interface expected by mixins.

GovernanceMixin and SovereigntyMixin are designed to be mixed into Kernel.
They reference attributes (emit_event, _db, read_events, _sync_memory_index)
that are defined on Kernel itself.  Declaring this Protocol allows mypy to
understand the contract without circular imports.
"""

from __future__ import annotations

from typing import Any, Protocol

from .event import Event


class _KernelMixinInterface(Protocol):
    """Minimal Kernel surface needed by GovernanceMixin + SovereigntyMixin.

    NOTE: This is deliberately incomplete — mypy treats un-declared attributes
    on Protocol types as Any, which is acceptable for mixin type-checking.
    Only the most commonly referenced methods are declared.
    """

    _db: Any

    def emit_event(
        self,
        type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object] | None = None,
        actor: str = "system",
        caused_by: str | None = None,
        correlation_id: str | None = None,
    ) -> Event: ...

    def read_events(
        self,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        type: str | None = None,
        types: list[str] | None = None,
        correlation_id: str | None = None,
        since_seq: int = 0,
        since_ts: str | None = None,
        payload_goal_id: str | None = None,
        limit: int | None = None,
        order: str = "asc",
    ) -> list[Event]: ...

    def _sync_memory_index(self, event: Event) -> None: ...
    def rebuild(self, aggregate_type: str, agent_id: str = "kernel") -> int: ...
    def rebuild_all(self) -> dict[str, int]: ...
