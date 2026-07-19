"""MCP Client Hub — manages tool registration, discovery, and invocation.

Supports both sync and async tool handlers. Builtin tool wiring lives in
``mcp_builtin_registration`` (extracted to keep this file within the
Architecture Contract God Object budget).
"""

import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from app.core.runtime.runtime_container import _LazyProxy, runtime

logger = logging.getLogger(__name__)


@dataclass
class ToolDef:
    """Definition of a tool that can be called by the LLM."""

    name: str
    description: str
    parameters: dict
    handler: Callable[..., str | Awaitable[str]]
    is_async: bool = False
    requires_confirmation: bool = False


def _filter_tool_kwargs(handler: Callable[..., Any], arguments: dict) -> dict:
    """Drop unexpected kwargs when the handler has a fixed signature.

    Handlers that accept ``**kwargs`` (e.g. mesh proxies) keep all arguments.
    """
    try:
        sig = inspect.signature(handler)
    except (TypeError, ValueError):
        return arguments
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return arguments
    allowed = {
        name
        for name, p in sig.parameters.items()
        if p.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    }
    return {k: v for k, v in arguments.items() if k in allowed}


class MCPHub:
    """Central hub for managing tools and routing LLM tool calls."""

    # Categories registered by default — the lean core that every chat turn
    # sees. Keeping this small saves prompt tokens and shrinks the attack
    # surface (write-class tools visible to the model).
    CORE_CATEGORIES: frozenset[str] = frozenset({
        "time", "filesystem", "web", "calendar", "email",
        "shell", "git", "goals",
    })
    # Advanced categories that depend on host GUI/messaging/hardware and are
    # therefore opt-in via settings.builtin_tool_categories.
    # Browser automation lives in the external Playwright MCP, not builtins.
    ADVANCED_CATEGORIES: frozenset[str] = frozenset({
        "telegram", "computer_use", "voice", "clipboard_ocr",
    })

    def __init__(self, enabled_categories: set[str] | None = None):
        self._tools: dict[str, ToolDef] = {}
        if enabled_categories is None:
            try:
                from app.config import settings
                raw = settings.builtin_tool_categories.strip()
            except Exception:
                raw = ""
            # Opt-in categories are *added* to CORE — listing ``telegram``
            # must not drop filesystem/shell/etc.
            opt_in = {c.strip() for c in raw.split(",") if c.strip()} if raw else set()
            enabled_categories = set(self.CORE_CATEGORIES) | opt_in
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
        """Return OpenAI-style tool schemas visible to the model.

        Forbidden capabilities are omitted so they neither consume prompt
        tokens nor appear as callable options.
        """
        from app.core.runtime.capability_governance import capability_governance

        defs: list[dict] = []
        for t in self._tools.values():
            if capability_governance.is_forbidden(t.name):
                continue
            defs.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            })
        return defs

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

        kwargs = _filter_tool_kwargs(tool.handler, arguments)
        try:
            if tool.is_async:
                result = await cast(Awaitable[str], tool.handler(**kwargs))
            else:
                result = cast(str, tool.handler(**kwargs))

            # tool_calls is a governed projection. Capability* events emitted
            # by kernel.invoke_capability flow through projectors_telemetry
            # (in projectors_governance), which owns the
            # INSERT. Recording here was a dual-write that could drift.

            if isinstance(result, str) and len(result) > 8000:
                result = result[:8000] + "\n... [output truncated]"
            return result
        except TypeError as e:
            logger.warning("Tool %s invalid arguments: %s", name, e)
            return json.dumps({"error": f"Invalid arguments for {name}: {e}"})
        except Exception as e:
            logger.exception("Tool %s failed", name)
            return json.dumps({"error": str(e)})


# Singleton — lazy proxy to RuntimeContainer so runtime.reset() rebuilds it.
if TYPE_CHECKING:
    mcp_hub: MCPHub
else:
    mcp_hub = _LazyProxy(lambda: runtime.mcp_hub)
