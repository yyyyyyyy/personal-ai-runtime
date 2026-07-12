#!/usr/bin/env python
"""Capability policy consistency guard.

Fails CI when a builtin tool's ``requires_confirmation`` flag disagrees with
the risk classification in ``capability_policy.json``. This closes the
dual-source-of-truth drift between:

  * ``ToolDef.requires_confirmation`` (set in mcp_builtin_registration.py) —
    the hub-layer fallback used only when no policy row exists.
  * ``capability_policy.json`` → seeded into ``policy_events`` — the
    authoritative risk source the 3-gate governance consults.

Rule (policy is authoritative):
  - A tool with ``requires_confirmation=True`` MUST appear in the policy's
    ``needs_user`` or ``forbidden`` list.
  - A tool in the policy's ``auto_allow`` list MUST NOT be marked
    ``requires_confirmation=True``.

The check builds an ``MCPHub`` with ALL categories enabled (core + advanced)
so computer_use / voice / clipboard_ocr tools are included.

Exit code 0 = consistent; 1 = drift detected.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
POLICY_PATH = BACKEND_DIR / "capability_policy.json"


def _load_policy(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "auto_allow": set(data.get("auto_allow", [])),
        "needs_user": set(data.get("needs_user", [])),
        "forbidden": set(data.get("forbidden", [])),
    }


def _build_hub_with_all_categories():
    """Build an MCPHub with core + advanced categories so every tool registers."""
    os.environ.setdefault("MCP_EXTERNAL_ENABLED", "false")
    os.environ.setdefault("LLM_API_KEY", "check-only")
    # Ensure backend is importable.
    sys.path.insert(0, str(BACKEND_DIR))
    from app.core.harness.mcp_hub import MCPHub  # noqa: E402

    all_categories = MCPHub.CORE_CATEGORIES | MCPHub.ADVANCED_CATEGORIES
    return MCPHub(enabled_categories=set(all_categories))


def check(quiet: bool = False) -> list[str]:
    """Return a list of human-readable drift descriptions (empty = consistent)."""
    policy = _load_policy(POLICY_PATH)
    hub = _build_hub_with_all_categories()

    drifts: list[str] = []
    for name in sorted(hub._tools):
        tool = hub._tools[name]
        wants_confirmation = tool.requires_confirmation
        in_needs_user = name in policy["needs_user"]
        in_forbidden = name in policy["forbidden"]
        in_auto_allow = name in policy["auto_allow"]

        # Rule 1: requires_confirmation=True must be backed by needs_user/forbidden.
        if wants_confirmation and not (in_needs_user or in_forbidden):
            drifts.append(
                f"{name}: requires_confirmation=True but not in "
                f"capability_policy.json needs_user/forbidden "
                f"(add to needs_user, or set requires_confirmation=False)"
            )

        # Rule 2: auto_allow tools must not demand confirmation.
        if in_auto_allow and wants_confirmation:
            drifts.append(
                f"{name}: in capability_policy.json auto_allow but "
                f"requires_confirmation=True "
                f"(auto_allow means no approval — drop requires_confirmation)"
            )

        # Rule 3: a tool missing from ALL policy lists is unclassified.
        if not (in_needs_user or in_forbidden or in_auto_allow):
            drifts.append(
                f"{name}: not classified in capability_policy.json "
                f"(add to auto_allow, needs_user, or forbidden)"
            )

    return drifts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if not args.quiet:
        print("Checking capability_policy.json vs ToolDef.requires_confirmation...")

    drifts = check(quiet=args.quiet)
    if drifts:
        print(f"FAIL: {len(drifts)} consistency drift(s) found:\n")
        for d in drifts:
            print(f"  - {d}")
        print(
            "\npolicy_events (seeded from capability_policy.json) is the "
            "authoritative risk source; ToolDef.requires_confirmation is only "
            "a fallback for tools without a policy row. Align the two."
        )
        return 1

    if not args.quiet:
        print("OK: capability policy and ToolDef flags are consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
