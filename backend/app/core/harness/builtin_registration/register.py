"""Category builder table and registration entry points."""

from __future__ import annotations

from collections.abc import Callable

from app.core.harness.builtin_registration.common import BuiltinToolSpec, _register_specs
from app.core.harness.builtin_registration.specs_core import (
    _filesystem_specs,
    _git_specs,
    _shell_specs,
    _time_specs,
    _web_specs,
)
from app.core.harness.builtin_registration.specs_domain import (
    _calendar_specs,
    _clipboard_ocr_specs,
    _computer_use_specs,
    _email_specs,
    _goals_specs,
    _telegram_specs,
    _voice_specs,
)
from app.core.harness.mcp_hub import ToolDef


def _register_all_tools(hub) -> None:
    for category, builder in _CATEGORY_BUILDERS.items():
        if category in hub._enabled_categories:
            _register_specs(hub, builder())


_CATEGORY_BUILDERS: dict[str, Callable[[], list[BuiltinToolSpec]]] = {
    # Core
    "time": _time_specs,
    "filesystem": _filesystem_specs,
    "web": _web_specs,
    "calendar": _calendar_specs,
    "email": _email_specs,
    "shell": _shell_specs,
    "git": _git_specs,
    "goals": _goals_specs,
    # Advanced (opt-in)
    "telegram": _telegram_specs,
    "clipboard_ocr": _clipboard_ocr_specs,
    "computer_use": _computer_use_specs,
    "voice": _voice_specs,
}


def register_mesh_tools(hub, discovered: list) -> int:
    """Register tools discovered from external MCP servers."""
    from app.core.harness.mcp_mesh import mcp_mesh
    from app.core.runtime.capability_governance import capability_governance
    from app.core.runtime.taint import (
        register_external_ingestion_tool,
        register_external_write_tool,
    )

    count = 0
    for item in discovered:
        registered_name = item.registered_name
        capability_governance.register_external_tool(
            registered_name,
            risk=item.policy_risk,
        )
        # Forbidden tools stay in governance (deny) but are not exposed to the
        # LLM schema or invokable via the hub handler table.
        if item.policy_risk == "forbidden":
            continue

        async def _handler(_name: str = registered_name, **kwargs) -> str:
            return await mcp_mesh.call_tool(_name, kwargs)

        hub.register_tool(ToolDef(
            name=registered_name,
            description=item.description,
            parameters=item.parameters,
            handler=_handler,
            is_async=True,
            requires_confirmation=item.requires_confirmation,
        ))
        if item.is_ingestion:
            register_external_ingestion_tool(registered_name)
        if item.requires_confirmation:
            register_external_write_tool(registered_name)
        count += 1
    return count
