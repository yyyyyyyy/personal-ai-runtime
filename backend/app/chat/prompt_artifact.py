"""Prompt Artifact — static model instructions for PromptCompiler.

Canonical source for identity, coding rules, and tool hints.

Identity and coding rules are loaded from prompt files in backend/prompts/.
Users can customize them via Settings > System Prompt.

Prompt Artifact is static guidance only — no DB, memory, kernel state, or events
(beyond optional runtime prompt overrides from app_settings).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.agents.tool_postprocess import build_prompt_hints
from app.core.runtime.governance.context_policy import CompileStage, analyze_intent_tags

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

# Tools whose presence (plus coding intent / post_tool) warrants coding rules.
_CODING_TOOLS = frozenset(
    {
        "apply_patch",
        "write_file",
        "read_file",
        "list_directory",
        "search_files",
        "shell_exec",
        "git_diff",
    }
)

# Current prompt hints are mail-oriented and relatively long — gate by intent.
_MAIL_HINT_TOOLS = frozenset(
    {
        "check_inbox",
        "read_inbox_email",
        "mark_inbox_email_read",
        "mark_inbox_email_unread",
    }
)

_OPS_KEYWORDS = re.compile(
    r"(?i)(\bmcp\b|filesystem|file\s*system|external[_\s-]?server|mcp_config|"
    r"FILESYSTEM_|\.env\.example)"
)

# ── Emergency fallbacks (only if prompt files are missing) ─────────────────

_FALLBACK_IDENTITY = (
    "You are Personal AI Runtime — a personal AI assistant. "
    "Be helpful, honest, and concise. All tool calls go through Runtime governance."
)

_FALLBACK_CODING_RULES = (
    "Coding & project changes:\n"
    "- The project root is: {project_root}. Use paths relative to this root.\n"
    "- Prefer apply_patch for small edits; use write_file for new files or full rewrites.\n"
    "- Do not edit kernel/, capability_policy.json, taint.py, check_boundary.py, .env, or .git/."
)

_FALLBACK_CODING_OPS = (
    "Ops notes (filesystem / MCP):\n"
    "- Restart the backend after changing FILESYSTEM_* env vars or mcp_config.json."
)


def _load_prompt_file(filename: str, default: str) -> str:
    """Load a prompt from a file, falling back to default if missing."""
    path = PROMPTS_DIR / filename
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return default


def render_coding_rules(template: str, project_root: str) -> str:
    """Substitute ``{project_root}`` without treating other braces as format fields.

    User-customized prompts may contain JSON/example ``{...}`` blocks that would
    crash ``str.format``.
    """
    return template.replace("{project_root}", project_root)


def should_include_coding_rules(
    *,
    stage: CompileStage,
    intent_tags: frozenset[str],
    available_tools: list[str] | set[str],
) -> bool:
    """Coding rules are heavy — inject only when likely useful."""
    if stage == "brief":
        return False
    tools = set(available_tools)
    if not (tools & _CODING_TOOLS):
        return False
    if "coding" in intent_tags:
        return True
    # Short resume messages ("继续") often lack coding keywords.
    return stage == "post_tool"


def should_include_coding_ops(*, user_message: str) -> bool:
    """Inject MCP/filesystem ops notes only when the turn is about them."""
    return bool(_OPS_KEYWORDS.search(user_message or ""))


def tools_for_prompt_hints(
    *,
    stage: CompileStage,
    intent_tags: frozenset[str],
    available_tools: list[str] | set[str],
) -> set[str]:
    """Filter tools whose prompt hints should be injected this turn."""
    if stage == "brief":
        return set()
    tools = set(available_tools)
    # Mail hints are long; keep on post_tool (walkthrough: 继续/下一封).
    if "mail" not in intent_tags and stage != "post_tool":
        tools -= _MAIL_HINT_TOOLS
    return tools


@lru_cache(maxsize=1)
def _load_capability_policy() -> dict[str, Any]:
    try:
        from app.config import settings

        path = Path(settings.capability_policy_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.debug("capability_policy unavailable for prompt notes: %s", exc)
        return {}


def build_policy_tool_notes() -> str:
    """Compact live tool lists from capability_policy.json (keeps identity.md short)."""
    policy = _load_capability_policy()
    needs = [str(x) for x in policy.get("needs_user", []) if x]
    external = [str(x) for x in policy.get("external_ingestion", []) if x]
    if not needs and not external:
        return ""
    lines = ["# Live governance tool lists (from capability_policy.json)"]
    if needs:
        lines.append("Gated side-effect tools (need confirmation): " + ", ".join(needs))
    if external:
        lines.append("External/untrusted content tools: " + ", ".join(external))
    return "\n".join(lines)


# Public constants (used by tests and callers)
IDENTITY_FILE = "identity.md"
CODING_RULES_FILE = "coding_rules.md"
CODING_RULES_OPS_FILE = "coding_rules_ops.md"

# Canonical prompt text: backend/prompts/*.md (fallback only if missing).
IDENTITY_ARTIFACT = _load_prompt_file(IDENTITY_FILE, _FALLBACK_IDENTITY)
CODING_RULES_TEMPLATE = _load_prompt_file(CODING_RULES_FILE, _FALLBACK_CODING_RULES)
CODING_RULES_OPS_TEMPLATE = _load_prompt_file(CODING_RULES_OPS_FILE, _FALLBACK_CODING_OPS)

# Settings UI should show the same defaults the chat compiler uses (core rules only).
DEFAULT_IDENTITY = IDENTITY_ARTIFACT
DEFAULT_CODING_RULES = CODING_RULES_TEMPLATE


# Runtime prompt override cache (app_settings). Cleared on save/invalidate.
_runtime_prompt_cache: dict[str, str | None] = {}


@dataclass
class PromptArtifactContext:
    available_tools: list[str]
    project_root: str
    stage: CompileStage
    user_message: str = ""
    intent_tags: frozenset[str] | None = None


class PromptArtifactLoader:
    """Load static prompt artifact blocks. No runtime state retrieval.

    Identity and coding rules can be overridden via:
    - backend/prompts/identity.md and coding_rules.md (file-based)
    - /api/settings/prompt API (runtime override, stored in app_settings)

    Ops appendix (coding_rules_ops.md) and live policy tool lists are always
    loaded from disk / capability_policy.json — not user-customizable.
    """

    async def load(self, ctx: PromptArtifactContext) -> str:
        intent_tags = ctx.intent_tags
        if intent_tags is None:
            intent_tags = analyze_intent_tags(ctx.user_message)

        identity = _load_runtime_prompt("identity") or IDENTITY_ARTIFACT
        parts: list[str] = [identity]

        policy_notes = build_policy_tool_notes()
        if policy_notes:
            parts.append(policy_notes)

        if should_include_coding_rules(
            stage=ctx.stage,
            intent_tags=intent_tags,
            available_tools=ctx.available_tools,
        ):
            coding_rules = _load_runtime_prompt("coding_rules") or CODING_RULES_TEMPLATE
            parts.append(render_coding_rules(coding_rules, ctx.project_root))
            if should_include_coding_ops(user_message=ctx.user_message):
                parts.append(CODING_RULES_OPS_TEMPLATE)

        hint_tools = tools_for_prompt_hints(
            stage=ctx.stage,
            intent_tags=intent_tags,
            available_tools=ctx.available_tools,
        )
        hints = build_prompt_hints(hint_tools)
        if hints:
            parts.append(hints)

        return "\n\n".join(parts)


def _load_runtime_prompt(key: str) -> str | None:
    """Load a prompt override from the runtime_config (app_settings table)."""
    if key in _runtime_prompt_cache:
        return _runtime_prompt_cache[key]
    try:
        from app.core.runtime.runtime_config import runtime_config

        value = runtime_config.get_prompt(key)
    except Exception:
        value = None
    _runtime_prompt_cache[key] = value
    return value


def invalidate_prompt_artifact_cache() -> None:
    """Clear cached runtime prompt overrides (tests / Settings save)."""
    _runtime_prompt_cache.clear()
    _load_capability_policy.cache_clear()


prompt_artifact_loader = PromptArtifactLoader()
