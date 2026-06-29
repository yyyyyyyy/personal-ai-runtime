"""Prompt Artifact — static model instructions for PromptCompiler.

Canonical source for identity, coding rules, and tool hints.

Migration notes:
  Canonical:   PromptArtifactLoader / IDENTITY_ARTIFACT / CODING_RULES_TEMPLATE
  Removed:     runtime.identity fragment (identity only via PromptArtifactLoader)

Prompt Artifact is static guidance only — no DB, memory, kernel state, or events.

Since v0.1.0: Identity and coding rules are loaded from prompt files in
backend/prompts/. Users can customize them via Settings > System Prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.agents.tool_postprocess import build_prompt_hints

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

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
- Protected from agent writes: kernel/, check_boundary.py, capability_policy.json, capability_policy.py, taint.py, sensitive_router.py, secret .env files (.env, .env.local, …), and .git/. You may edit .env.example and backend/mcp_config.json.
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


# Keep backward-compatible constants (used by tests and legacy code)
IDENTITY_FILE = "identity.md"
CODING_RULES_FILE = "coding_rules.md"

# Load defaults from files or constants
IDENTITY_ARTIFACT = _load_prompt_file(IDENTITY_FILE, DEFAULT_IDENTITY)
CODING_RULES_TEMPLATE = _load_prompt_file(CODING_RULES_FILE, DEFAULT_CODING_RULES)


@dataclass
class PromptArtifactContext:
    available_tools: list[str]
    project_root: str
    stage: str


class PromptArtifactLoader:
    """Load static prompt artifact blocks. No runtime state retrieval.

    Since v0.1.0, identity and coding rules can be overridden via:
    - backend/prompts/identity.md and coding_rules.md (file-based)
    - /api/settings/prompt API (runtime override, stored in app_settings)
    """

    async def load(self, ctx: PromptArtifactContext) -> str:
        # Check for runtime-overridden prompts (from app_settings)
        identity = _load_runtime_prompt("identity") or IDENTITY_ARTIFACT
        coding_rules = _load_runtime_prompt("coding_rules") or CODING_RULES_TEMPLATE

        parts: list[str] = [identity]
        parts.append(coding_rules.format(project_root=ctx.project_root))

        hints = build_prompt_hints(set(ctx.available_tools))
        if hints:
            parts.append(hints)

        return "\n\n".join(parts)


def _load_runtime_prompt(key: str) -> str | None:
    """Load a prompt override from the runtime_config (app_settings table)."""
    try:
        from app.core.runtime.runtime_config import runtime_config

        return runtime_config.get_prompt(key)
    except Exception:
        return None


prompt_artifact_loader = PromptArtifactLoader()
