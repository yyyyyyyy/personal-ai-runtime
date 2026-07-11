"""Reaction Registry — declarative periodic actions.

v0.6.0: Imperative TriggerEngine replaced by @reaction declarations.
v0.11.0: removed unused event-driven ``on_event``/``_check_threshold`` path
         (it was never wired into Kernel._dispatch). ``evaluate_cycle`` is
         now the only firing mechanism.

A Reaction is registered with declarative metadata (``ReactionWhen``) and a
handler. The runtime invokes ``evaluate_cycle`` periodically (via
RuntimeLoop._maintenance); handlers receive the Kernel and must perform their
own condition checks internally — ``ReactionWhen`` fields are surfaced via
``list_reactions`` and the Triggers API but do NOT gate firing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from app.core.runtime.kernel.event import Event
    from app.core.runtime.kernel.kernel import Kernel


@dataclass
class ReactionWhen:
    """Condition describing when a Reaction should fire."""
    event_type: str = ""
    event_types: list[str] = field(default_factory=list)
    aggregate_type: str = ""
    count_gte: int = 0          # threshold: fire after N events in window
    window_days: int = 1        # rolling window for threshold
    payload_check: dict[str, Any] = field(default_factory=dict)

    def matches_event(self, event: "Event") -> bool:
        types = self.event_types if self.event_types else ([self.event_type] if self.event_type else [])
        if types and event.type not in types:
            return False
        if self.aggregate_type and event.aggregate_type != self.aggregate_type:
            return False
        return True


@dataclass
class ReactionThen:
    """Action to produce when a Reaction fires."""
    notification_template: str = ""  # e.g. "收件箱积压 {count} 封"
    notification_title: str = ""
    notification_severity: str = "info"
    emit_event_type: str = ""       # emit a new event type when triggered


class Reaction:
    """A single declarative Reaction — condition + action."""

    def __init__(
        self,
        name: str,
        handler: Callable | None = None,
        when: ReactionWhen | None = None,
        then: ReactionThen | None = None,
    ):
        self.name = name
        self.handler = handler
        self.when = when or ReactionWhen()
        self.then = then or ReactionThen()

    def matches(self, event: "Event") -> bool:
        return self.when.matches_event(event)


class ReactionRegistry:
    """Manages declared Reactions and evaluates them periodically.

    Only ``evaluate_cycle`` is wired into the runtime (via
    ``RuntimeLoop._maintenance``). It unconditionally invokes every Reaction
    whose ``count_gte > 0`` and which has a handler, passing the Kernel as
    the sole argument. ``ReactionWhen`` fields (``event_type``, ``window_days``,
    ``payload_check``…) are declarative metadata surfaced via ``list_reactions``
    and the Triggers API, but are NOT consulted by the evaluator — handlers
    must perform their own condition checks internally.

    An earlier ``on_event`` event-driven path existed but was never wired into
    Kernel._dispatch; it was removed to avoid giving the impression that
    ``ReactionWhen`` fields drive firing.
    """

    def __init__(self):
        self._reactions: dict[str, Reaction] = {}

    def register(self, reaction: Reaction) -> None:
        self._reactions[reaction.name] = reaction

    def evaluate_cycle(self, kernel: "Kernel") -> int:
        """Called periodically by RuntimeLoop to process timer-based reactions.

        Returns number of reactions that fired.
        """
        fired = 0
        # Timer-based reactions include staleness checks, etc.
        # This is the replacement for the old trigger_engine.evaluate_and_notify().
        for reaction in self._reactions.values():
            if reaction.when.count_gte > 0 and reaction.handler:
                try:
                    reaction.handler(kernel)
                    fired += 1
                except Exception:
                    import logging
                    logging.getLogger(__name__).warning(
                        "Periodic reaction handler failed for %s", reaction.name, exc_info=True
                    )
        return fired

    def list_reactions(self) -> list[dict]:
        return [
            {"name": r.name, "when_type": r.when.event_type,
             "when_aggregate": r.when.aggregate_type,
             "threshold": r.when.count_gte,
             "has_handler": r.handler is not None}
            for r in self._reactions.values()
        ]


# ── Decorator ──────────────────────────────────────────────────────────────

_reaction_registry = ReactionRegistry()


def reaction(
    when: ReactionWhen | None = None,
    then: ReactionThen | None = None,
    *,
    name: str | None = None,
):
    """Decorator to register a Reaction.

    Example:
        @reaction(
            when=ReactionWhen(count_gte=1),
            then=ReactionThen(notification_template="..."),
        )
        def my_check(kernel=None):
            ...
    """
    def decorator(handler):
        r_name = name or handler.__name__
        _reaction_registry.register(Reaction(r_name, handler, when=when, then=then))
        return handler
    return decorator


def get_reaction_registry() -> ReactionRegistry:
    return _reaction_registry


def reset_reactions() -> None:
    """Clear all registered reactions — for test isolation.

    Called by RuntimeContainer.reset() so tests do not leak reactions into
    each other. Module-level registry is rebuilt lazily on the next @reaction
    decoration or import of builtin_reactions.
    """
    _reaction_registry._reactions.clear()
