"""Reaction Registry — declarative event→action bindings replacing TriggerEngine.

v0.6.0: Imperative TriggerEngine replaced by @reaction declarations.
A Reaction is a pure composition of Runtime Algebra primitives:
    Reaction = subscribe(Event) + invoke(Capability) + produce(Work)

Usage:
    @reaction(
        when=Event(type="InboxEmailRecorded", count_gte=50, window_days=1),
        then=Notification(template="收件箱积压 {count} 封"),
    )
    def email_backlog(event, ctx):
        ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    """Manages declared Reactions and evaluates them on events."""

    def __init__(self):
        self._reactions: dict[str, Reaction] = {}
        self._counters: dict[str, tuple[int, str]] = {}  # name → (count, last_reset_iso)

    def register(self, reaction: Reaction) -> None:
        self._reactions[reaction.name] = reaction

    def on_event(self, event: "Event") -> None:
        """Called on every emitted event to evaluate matching Reactions."""
        for reaction in self._reactions.values():
            if not reaction.matches(event):
                continue
            if reaction.when.count_gte > 0:
                if not self._check_threshold(reaction, event):
                    continue
            # Fire the reaction
            if reaction.handler:
                try:
                    reaction.handler(event)
                except Exception:
                    import logging
                    logging.getLogger(__name__).warning(
                        "Reaction handler failed for %s", reaction.name, exc_info=True
                    )

    def _check_threshold(self, reaction: Reaction, event: "Event") -> bool:
        """Track rolling counter per reaction; return True when threshold met."""
        key = f"react_cnt_{reaction.name}"
        now_iso = datetime.now(UTC).isoformat()
        count, last_reset = self._counters.get(key, (0, now_iso))

        try:
            last_dt = datetime.fromisoformat(last_reset)
            if (datetime.now(UTC) - last_dt).total_seconds() > reaction.when.window_days * 86400:
                count = 0
                last_reset = now_iso
        except (ValueError, TypeError):
            count = 0
            last_reset = now_iso

        count += 1
        self._counters[key] = (count, last_reset)

        # Only fire at exact threshold, not every event above it
        return count == reaction.when.count_gte

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
            when=ReactionWhen(event_type="InboxEmailRecorded", count_gte=50, window_days=1),
            then=ReactionThen(notification_template="收件箱积压 {count} 封"),
        )
        def email_backlog(event_or_kernel=None):
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
    """Clear all registered reactions and counters — for test isolation.

    Called by RuntimeContainer.reset() so tests do not leak reactions into
    each other. Module-level registry is rebuilt lazily on the next @reaction
    decoration or import of builtin_reactions.
    """
    _reaction_registry._reactions.clear()
    _reaction_registry._counters.clear()
