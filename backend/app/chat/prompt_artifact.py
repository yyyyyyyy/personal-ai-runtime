"""Prompt Artifact — static model instructions for PromptCompiler.

Canonical source for identity, coding rules, and tool hints.

Identity and coding rules are loaded from prompt files in backend/prompts/.
Users can customize them via Settings > System Prompt.

Prompt Artifact is static guidance only — no DB, memory, kernel state, or events
(beyond optional runtime prompt overrides from app_settings).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.agents.tool_postprocess import build_prompt_hints
from app.core.runtime.governance.context_policy import CompileStage, analyze_intent_tags

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

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

# ── Default identity (fallback if prompt file is missing) ─────────────────

DEFAULT_IDENTITY = """You are Personal AI Runtime — a personal AI assistant that helps users manage their life, work, and goals.

You are:
- Helpful: Provide clear, actionable responses.
- Honest: Admit when you don't know something. Never fabricate information.
- Proactive: When you see an opportunity to help, use tools.
- Concise: Get to the point. Users value brevity.

Memories may appear in two sections:
- Self-reported facts: the user's own words; treat as authoritative.
- System hypotheses: with confidence scores; NOT definitive statements.
When self-report and system hypothesis conflict, defer to self-report.

Use available tools when they help answer the user's query.
All tool invocations go through the Runtime's governance layer."""

# ── Default coding rules (fallback) ───────────────────────────────────────

DEFAULT_CODING_RULES = """Coding & project changes:
- The project root is: {project_root}. Use this as the base for all file paths. Never use absolute paths like /README.md or /root/ — always construct paths relative to the project root.
- Before editing code, read relevant files with read_file and inspect changes with git_diff when useful.
- Prefer apply_patch for small edits; use write_file only for new files or full rewrites.
- After code changes, suggest running tests via shell_exec (e.g. make test-backend).
- Protected from agent writes: kernel/, check_boundary.py, capability_policy.json, taint.py, sensitive_router.py, secret .env files (.env, .env.local, …), and .git/. You may edit .env.example and backend/mcp_config.json.
- Filesystem tool settings load at backend startup — after changing FILESYSTEM_* env vars, restart the backend.
- To add an external MCP: edit backend/mcp_config.json (follow existing external_servers entries), update .env.example if needed, tell the user which .env keys to set, and remind them to restart the backend before new tools appear.

shell_exec rules:
- Use list_directory and read_file to explore the project — do not use shell_exec to list files."""


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


# Public constants (used by tests and callers)
IDENTITY_FILE = "identity.md"
CODING_RULES_FILE = "coding_rules.md"

# Load defaults from files or constants
IDENTITY_ARTIFACT = _load_prompt_file(IDENTITY_FILE, DEFAULT_IDENTITY)
CODING_RULES_TEMPLATE = _load_prompt_file(CODING_RULES_FILE, DEFAULT_CODING_RULES)

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
    """

    async def load(self, ctx: PromptArtifactContext) -> str:
        intent_tags = ctx.intent_tags
        if intent_tags is None:
            intent_tags = analyze_intent_tags(ctx.user_message)

        identity = _load_runtime_prompt("identity") or IDENTITY_ARTIFACT
        parts: list[str] = [identity]

        if should_include_coding_rules(
            stage=ctx.stage,
            intent_tags=intent_tags,
            available_tools=ctx.available_tools,
        ):
            coding_rules = _load_runtime_prompt("coding_rules") or CODING_RULES_TEMPLATE
            parts.append(render_coding_rules(coding_rules, ctx.project_root))

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


prompt_artifact_loader = PromptArtifactLoader()
