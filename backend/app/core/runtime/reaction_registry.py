"""Reaction Registry — declarative periodic actions.

Reactions are declared via ``@reaction`` and fired by ``evaluate_cycle``.
``ReactionWhen`` is consulted by ``evaluate_cycle``:
         - ``every_cycle`` opts a reaction into the periodic loop.
         - ``state_selector`` + ``count_gte`` (+ optional ``state_filters``)
           are a pre-gate: the handler is skipped when matching state rows
           are below the threshold.
         - ``event_type`` / ``window_days`` / ``payload_check`` remain
           descriptive metadata for the Triggers API (not yet an event bus).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from app.core.runtime.kernel.event import Event
    from app.core.runtime.kernel.kernel import Kernel


@dataclass
class ReactionWhen:
    """Conditions that gate periodic evaluation.

    ``every_cycle``
        Include this reaction in RuntimeLoop ``evaluate_cycle``.

    ``state_selector`` / ``state_filters`` / ``count_gte``
        Pre-gate against governed state via ``kernel.query_state``. When
        ``state_selector`` is set and ``count_gte > 0``, the handler is only
        invoked if at least ``count_gte`` rows match.

    ``event_type`` / ``event_types`` / ``aggregate_type`` / ``window_days`` /
    ``payload_check``
        Descriptive metadata (Triggers API / future event-driven paths).
        Not consulted by ``evaluate_cycle``.
    """

    every_cycle: bool = False
    state_selector: str = ""
    state_filters: dict[str, Any] = field(default_factory=dict)
    count_gte: int = 0
    event_type: str = ""
    event_types: list[str] = field(default_factory=list)
    aggregate_type: str = ""
    window_days: int = 1
    payload_check: dict[str, Any] = field(default_factory=dict)

    def matches_event(self, event: "Event") -> bool:
        types = self.event_types if self.event_types else ([self.event_type] if self.event_type else [])
        if types and event.type not in types:
            return False
        if self.aggregate_type and event.aggregate_type != self.aggregate_type:
            return False
        return True

    def is_periodic(self) -> bool:
        """Whether this reaction participates in ``evaluate_cycle``."""
        if self.every_cycle:
            return True
        # Opt-in via count_gte > 0 without every_cycle.
        if self.count_gte > 0:
            return True
        if self.state_selector:
            return True
        return False


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

    ``evaluate_cycle`` (via ``RuntimeLoop._maintenance``):
      1. Skip reactions without a handler or not marked periodic.
      2. If ``state_selector`` + ``count_gte`` are set, query state and skip
         when below threshold.
      3. Invoke the handler with the Kernel.
    """

    def __init__(self):
        self._reactions: dict[str, Reaction] = {}

    def register(self, reaction: Reaction) -> None:
        self._reactions[reaction.name] = reaction

    def _state_gate_passes(self, reaction: Reaction, kernel: "Kernel") -> bool:
        """Return False when a state threshold is configured and not met."""
        when = reaction.when
        if not when.state_selector or when.count_gte <= 0:
            return True
        try:
            rows = kernel.query_state(
                when.state_selector,
                limit=when.count_gte,
                **when.state_filters,
            )
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "Reaction state gate query failed for %s", reaction.name, exc_info=True,
            )
            return False
        return len(rows) >= when.count_gte

    def evaluate_cycle(self, kernel: "Kernel") -> int:
        """Called periodically by RuntimeLoop to process timer-based reactions.

        Returns number of reactions whose handlers were invoked (after gates).
        """
        fired = 0
        for reaction in self._reactions.values():
            if not reaction.handler or not reaction.when.is_periodic():
                continue
            if not self._state_gate_passes(reaction, kernel):
                continue
            try:
                reaction.handler(kernel)
                fired += 1
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    "Periodic reaction handler failed for %s", reaction.name, exc_info=True,
                )
        return fired

    def list_reactions(self) -> list[dict]:
        result = []
        for r in self._reactions.values():
            gated_by = "none"
            if r.when.state_selector and r.when.count_gte > 0:
                gated_by = "state"
            elif r.handler:
                gated_by = "handler"
            result.append({
                "name": r.name,
                "every_cycle": r.when.every_cycle or r.when.is_periodic(),
                "when_type": r.when.event_type,
                "when_aggregate": r.when.aggregate_type,
                "state_selector": r.when.state_selector,
                "threshold": r.when.count_gte,
                "gated_by": gated_by,
                "has_handler": r.handler is not None,
            })
        return result


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
            when=ReactionWhen(
                every_cycle=True,
                state_selector="inbox_emails",
                state_filters={"status": "pending"},
                count_gte=50,
            ),
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
