"""Minimal subprocess environment shared by shell and external MCP servers.

Never inherit the full parent process env — it commonly contains LLM_API_KEY,
EMAIL_PASS, and other secrets that must not leak into tool children.
"""

from __future__ import annotations

import os
import sys

# Locale / temp / identity keys that tools legitimately need, without pulling
# in credential-bearing variables from the parent process.
_BASE_KEYS = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "TMPDIR",
    "TMP",
    "TEMP",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "TZ",
)

_WIN_KEYS = (
    "SYSTEMROOT",
    "USERPROFILE",
    "COMSPEC",
    "PATHEXT",
)


def minimal_subprocess_env(*, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return a sanitized env suitable for ``subprocess.run`` / MCP stdio.

    ``extra`` is applied last (e.g. MCP server-specific API keys from settings).
    """
    env: dict[str, str] = {}
    for key in _BASE_KEYS:
        val = os.environ.get(key)
        if val:
            env[key] = val
    if sys.platform == "win32":
        for key in _WIN_KEYS:
            val = os.environ.get(key)
            if val:
                env[key] = val
    if "PATH" not in env:
        env["PATH"] = os.environ.get("PATH", "")
    if extra:
        for key, val in extra.items():
            if val:
                env[key] = val
    return env
