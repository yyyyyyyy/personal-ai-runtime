"""Compatibility shim — implementation lives in ``builtin_registration``.

Existing imports ``from app.core.harness.mcp_builtin_registration import ...``
and ``from app.core.harness import mcp_builtin_registration as reg`` keep working.
"""

from app.core.harness.builtin_registration import (  # noqa: F401
    _CATEGORY_BUILDERS,
    BuiltinToolSpec,
    _calendar_specs,
    _clipboard_ocr_specs,
    _computer_use_specs,
    _email_specs,
    _filesystem_specs,
    _git_specs,
    _goals_specs,
    _offload,
    _register_all_tools,
    _register_specs,
    _shell_specs,
    _telegram_specs,
    _time_specs,
    _voice_specs,
    _web_specs,
    register_mesh_tools,
)

__all__ = [
    "BuiltinToolSpec",
    "_CATEGORY_BUILDERS",
    "_calendar_specs",
    "_clipboard_ocr_specs",
    "_computer_use_specs",
    "_email_specs",
    "_filesystem_specs",
    "_git_specs",
    "_goals_specs",
    "_offload",
    "_register_all_tools",
    "_register_specs",
    "_shell_specs",
    "_telegram_specs",
    "_time_specs",
    "_voice_specs",
    "_web_specs",
    "register_mesh_tools",
]
