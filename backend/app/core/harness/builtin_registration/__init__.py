"""Builtin tool registration package.

Public surface mirrors the former ``mcp_builtin_registration`` module so
``mcp_hub`` and tests can keep importing the same names.
"""

from app.core.harness.builtin_registration.common import (
    BuiltinToolSpec,
    _offload,
    _register_specs,
)
from app.core.harness.builtin_registration.register import (
    _CATEGORY_BUILDERS,
    _register_all_tools,
    register_mesh_tools,
)
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
