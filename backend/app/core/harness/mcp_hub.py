"""MCP Client Hub — manages tool registration, discovery, and invocation.

Supports both sync and async tool handlers. Builtin tool wiring lives in
``mcp_builtin_registration`` (extracted to keep this file within the
Architecture Contract God Object budget).
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from app.core.runtime.runtime_container import _LazyProxy, runtime


@dataclass
class ToolDef:
    """Definition of a tool that can be called by the LLM."""

    name: str
    description: str
    parameters: dict
    handler: Callable[..., str | Awaitable[str]]
    is_async: bool = False
    requires_confirmation: bool = False


class MCPHub:
    """Central hub for managing tools and routing LLM tool calls."""

    # Categories registered by default — the lean core that every chat turn
    # sees. Keeping this small saves prompt tokens and shrinks the attack
    # surface (write-class tools visible to the model).
    CORE_CATEGORIES: frozenset[str] = frozenset({
        "time", "filesystem", "web", "calendar", "email", "browser",
        "shell", "git", "telegram", "goals",
    })
    # Advanced categories that depend on host GUI/hardware and are therefore
    # opt-in via settings.builtin_tool_categories.
    ADVANCED_CATEGORIES: frozenset[str] = frozenset({
        "computer_use", "voice", "clipboard_ocr",
    })

    def __init__(self, enabled_categories: set[str] | None = None):
        self._tools: dict[str, ToolDef] = {}
        if enabled_categories is None:
            try:
                from app.config import settings
                raw = settings.builtin_tool_categories.strip()
            except Exception:
                raw = ""
            if raw:
                enabled_categories = {c.strip() for c in raw.split(",") if c.strip()}
            else:
                enabled_categories = set(self.CORE_CATEGORIES)
        self._enabled_categories = enabled_categories
        self._register_all_tools()

    def _register_all_tools(self) -> None:
        from app.core.harness import mcp_builtin_registration as reg
        reg._register_all_tools(self)

    def register_mesh_tools(self, tool_defs: list) -> int:
        """Register tools discovered from the MCP Mesh. Returns count added."""
        from app.core.harness import mcp_builtin_registration as reg
        return reg.register_mesh_tools(self, tool_defs)

    def register_tool(self, tool: ToolDef):
        self._tools[tool.name] = tool

    def unregister_tool(self, name: str) -> None:
        self._tools.pop(name, None)

    def get_tool_defs_for_llm(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    def get_tool(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def needs_confirmation(self, name: str) -> bool:
        tool = self._tools.get(name)
        return tool.requires_confirmation if tool else False

    def is_async(self, name: str) -> bool:
        tool = self._tools.get(name)
        return tool.is_async if tool else False

    async def invoke_tool(self, name: str, arguments: dict) -> str:
        """Invoke a tool by name. Supports both sync and async handlers. Returns the result string."""
        tool = self._tools.get(name)
        if not tool:
            return json.dumps({"error": f"Unknown tool: {name}"})

        try:
            if tool.is_async:
                result = await cast(Awaitable[str], tool.handler(**arguments))
            else:
                result = cast(str, tool.handler(**arguments))

            # v0.3.0: tool_calls is now a governed projection. Capability*
            # events emitted by kernel.invoke_capability flow through
            # projectors_telemetry (in projectors_governance), which owns the
            # INSERT. Recording here was a dual-write that could drift.

            if isinstance(result, str) and len(result) > 8000:
                result = result[:8000] + "\n... [output truncated]"
            return result
        except Exception as e:
            return json.dumps({"error": str(e)})


# Singleton — lazy proxy to RuntimeContainer so runtime.reset() rebuilds it.
if TYPE_CHECKING:
    mcp_hub: MCPHub
else:
    mcp_hub = _LazyProxy(lambda: runtime.mcp_hub)
