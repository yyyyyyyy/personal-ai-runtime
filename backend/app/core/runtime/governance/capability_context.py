"""Capability Context — runtime snapshot for Capability-Aware Governance.

Provides the Governance Policy with a read-only view of current system
capabilities:
    - Which abstract capabilities are available (derived from tools)
    - Which capabilities are granted to the current principal
    - Which capabilities are unavailable (tools missing / denied)
    - Current runtime mode (normal / restricted / offline / maintenance)

Capability ≠ Tool. Capability is an abstraction layer. Tools are
implementation details. The Capability Registry maps tool names
to capability names.

This snapshot is built by CapabilityContextProvider from the Tool Registry,
Capability Registry, and Runtime Configuration. It is read-only.

Architecture:
    CapabilityContextProvider.build(...)
        ↓
    CapabilityContext (frozen, read-only snapshot)
        ↓
    Governance Policy.evaluate(request, execution_context, capability_context)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.core.runtime.execution import Principal

logger = logging.getLogger(__name__)

# TTL cache for tool definitions to avoid full table scans on hot path
_TOOL_CACHE_TTL = 30.0
_tool_cache: tuple[float, frozenset[str]] | None = None

# ── Runtime Mode ────────────────────────────────────────────────────────

RuntimeMode = Literal["normal", "restricted", "offline", "maintenance"]

_DEFAULT_RUNTIME_MODE: RuntimeMode = "normal"

# ── Capability names (abstract layer — NOT tool names) ───────────────────

SCHEDULING = "scheduling"
COMMUNICATION = "communication"
TASK_MANAGEMENT = "task_management"
KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
PLANNING = "planning"
MEMORY = "memory"

ALL_KNOWN_CAPABILITIES: frozenset[str] = frozenset({
    SCHEDULING,
    COMMUNICATION,
    TASK_MANAGEMENT,
    KNOWLEDGE_RETRIEVAL,
    PLANNING,
    MEMORY,
})

# ── Capability Registry: tool name → capability name ─────────────────────

_TOOL_TO_CAPABILITY: dict[str, str] = {
    # scheduling
    "list_calendar_events": SCHEDULING,
    "add_calendar_event": SCHEDULING,
    "get_upcoming_events": SCHEDULING,
    # communication
    "check_inbox": COMMUNICATION,
    "read_inbox_email": COMMUNICATION,
    "send_email": COMMUNICATION,
    "telegram_send": COMMUNICATION,
    "telegram_updates": COMMUNICATION,
    # knowledge_retrieval
    "web_search": KNOWLEDGE_RETRIEVAL,
    "fetch_url": KNOWLEDGE_RETRIEVAL,
    "search_files": KNOWLEDGE_RETRIEVAL,
    "search_and_extract": KNOWLEDGE_RETRIEVAL,
    # task_management
    "read_file": TASK_MANAGEMENT,
    "write_file": TASK_MANAGEMENT,
    "apply_patch": TASK_MANAGEMENT,
    "list_directory": TASK_MANAGEMENT,
    "shell_exec": TASK_MANAGEMENT,
    "git_status": TASK_MANAGEMENT,
    "git_log": TASK_MANAGEMENT,
    "git_diff": TASK_MANAGEMENT,
    "open_web_page": TASK_MANAGEMENT,
    "get_clipboard": TASK_MANAGEMENT,
    "ocr_image": TASK_MANAGEMENT,
    # memory (always present — not tool-bound)
    "get_current_time": MEMORY,
}

# ── Fragment ID → required capabilities ─────────────────────────────────

_FRAGMENT_REQUIRED_CAPABILITIES: dict[str, frozenset[str]] = {
    "calendar.today": frozenset({SCHEDULING}),
    "calendar.upcoming": frozenset({SCHEDULING}),
    "calendar.identity": frozenset({SCHEDULING}),
    "mail.recent_emails": frozenset({COMMUNICATION}),
    "mail.identity": frozenset({COMMUNICATION}),
    "mail.email_search": frozenset({COMMUNICATION}),
    "core.world": frozenset({PLANNING}),
    "core.goals": frozenset({PLANNING}),
    "core.actions": frozenset({TASK_MANAGEMENT}),
    "core.events": frozenset(),
    "core.memory": frozenset(),
    "core.conversation_state": frozenset(),
}

# ── Runtime mode → suppressed capabilities ──────────────────────────────

_RUNTIME_MODE_SUPPRESSIONS: dict[RuntimeMode, frozenset[str]] = {
    "normal": frozenset(),
    "offline": frozenset({KNOWLEDGE_RETRIEVAL, COMMUNICATION}),
    "restricted": frozenset({COMMUNICATION, SCHEDULING}),
    "maintenance": frozenset({SCHEDULING, COMMUNICATION, KNOWLEDGE_RETRIEVAL, PLANNING}),
}

# ── Capability Context (read-only snapshot) ──────────────────────────────


@dataclass(frozen=True)
class CapabilityContext:
    """Read-only capability snapshot consumed by Governance Policy.

    Frozen by design — Policy must not mutate capability state during
    context evaluation.

    available_capabilities: capabilities derived from currently registered tools
    granted_capabilities: capabilities granted to the current principal
    unavailable_capabilities: capabilities that would be needed but are absent
    runtime_mode: current operational mode
    """

    available_capabilities: tuple[str, ...] = field(default_factory=tuple)
    granted_capabilities: tuple[str, ...] = field(default_factory=tuple)
    unavailable_capabilities: tuple[str, ...] = field(default_factory=tuple)
    runtime_mode: RuntimeMode = _DEFAULT_RUNTIME_MODE

    @property
    def is_available(self) -> bool:
        """Returns True when at least one capability is available."""
        return bool(self.available_capabilities)

    def has_capability(self, capability: str) -> bool:
        """Check if a specific capability is available (granted + not suppressed by mode)."""
        suppressed = self._suppressed_by_mode()
        if capability in suppressed:
            return False
        return capability in self.available_capabilities or capability in self.granted_capabilities

    def _suppressed_by_mode(self) -> frozenset[str]:
        return _RUNTIME_MODE_SUPPRESSIONS.get(self.runtime_mode, frozenset())


_DEFAULT_CAPABILITY_SNAPSHOT = CapabilityContext()


# ── CapabilityContextProvider ────────────────────────────────────────────


class CapabilityContextProvider:
    """Builds a CapabilityContext snapshot from tool registry and runtime config.

    This is the ONLY component authorized to read the Tool Registry
    and translate tool names to capabilities for context policy purposes.
    Fragments, Assembler, and Pipeline are explicitly forbidden from
    reading Tool Registry directly.
    """

    def build(
        self,
        *,
        runtime_mode: RuntimeMode = _DEFAULT_RUNTIME_MODE,
        principal: "Principal | None" = None,
    ) -> CapabilityContext:
        """Build a CapabilityContext from current tool availability.

        Derives available capabilities from the MCP Hub tool registry,
        then subtracts capabilities suppressed by the current runtime mode.
        """
        available: set[str] = set()
        unavailable: set[str] = set()
        granted: set[str] = set()

        # 1. Derive available capabilities from tool registry (cached)
        try:
            from app.core.runtime.kernel_instance import kernel

            now = time.monotonic()
            global _tool_cache
            if _tool_cache is not None and now - _tool_cache[0] < _TOOL_CACHE_TTL:
                tool_names = _tool_cache[1]
            else:
                tool_defs = kernel.list_capability_definitions()
                names: set[str] = set()
                for tool_def in tool_defs:
                    tool_name = tool_def.get("function", {}).get("name", "")
                    if tool_name:
                        names.add(tool_name)
                _tool_cache = (now, frozenset(names))
                tool_names = _tool_cache[1]

            for tool_name in tool_names:
                capability = _TOOL_TO_CAPABILITY.get(tool_name)
                if capability:
                    available.add(capability)
        except Exception:
            logger.debug("Cannot read tool registry; using empty capability set", exc_info=True)

        # 2. Compute granted capabilities from principal
        if principal is not None:
            for cap in available:
                if principal.is_capable_of(cap):
                    granted.add(cap)

        # 3. Apply runtime mode suppressions
        mode_suppressions = _RUNTIME_MODE_SUPPRESSIONS.get(
            runtime_mode, frozenset()
        )
        effective_available = available - set(mode_suppressions)
        effective_granted = granted - set(mode_suppressions)

        # 4. Identify unavailable capabilities (all known minus what's available after mode filter)
        for cap_name in ALL_KNOWN_CAPABILITIES:
            if cap_name not in effective_available:
                unavailable.add(cap_name)

        return CapabilityContext(
            available_capabilities=tuple(sorted(effective_available)),
            granted_capabilities=tuple(sorted(effective_granted)),
            unavailable_capabilities=tuple(sorted(unavailable)),
            runtime_mode=runtime_mode,
        )


# ── Utility functions (used by policy) ────────────────────────────────────


def fragment_required_capabilities(fragment_id: str) -> frozenset[str]:
    """Return the capabilities a fragment requires (empty = always available)."""
    return _FRAGMENT_REQUIRED_CAPABILITIES.get(fragment_id, frozenset())


def capability_matched_by_user_intent(
    available_capabilities: tuple[str, ...],
    user_tags: frozenset[str],
) -> set[str]:
    """Determine which available capabilities match user intent tags.

    Maps user intent tags (from QueryAnalyzer) to capabilities.
    Returns the set of capabilities that are both available AND
    match the user's expressed intent.
    """
    # Tag → capability mapping
    _TAG_CAPABILITY_MAP: dict[str, str] = {
        "calendar": SCHEDULING,
        "mail": COMMUNICATION,
        "coding": TASK_MANAGEMENT,
        "knowledge": KNOWLEDGE_RETRIEVAL,
        "planning": PLANNING,
        "goals": PLANNING,
        "memory": MEMORY,
    }

    matched: set[str] = set()
    available_set = set(available_capabilities)

    for tag in user_tags:
        cap = _TAG_CAPABILITY_MAP.get(tag)
        if cap and cap in available_set:
            matched.add(cap)

    return matched


def runtime_mode_suppressed_capabilities(mode: RuntimeMode) -> frozenset[str]:
    """Return capabilities suppressed by a given runtime mode."""
    return _RUNTIME_MODE_SUPPRESSIONS.get(mode, frozenset())
