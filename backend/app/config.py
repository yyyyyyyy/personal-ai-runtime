"""Application configuration management using pydantic-settings."""

import logging
from pathlib import Path

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def resolve_project_path(value: str) -> str:
    """Resolve a path relative to repo root (BASE_DIR), not process cwd.

    Prevents ghost paths like backend/backend/data when uvicorn runs from backend/.
    """
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = (BASE_DIR / p).resolve()
    else:
        p = p.resolve()
    return str(p)


def validate_storage_paths(
    data_dir: str,
    sqlite_path: str,
    vector_dir: str,
) -> list[str]:
    """Return warnings for mis-resolved storage paths (e.g. backend/backend/data)."""
    warnings: list[str] = []
    for label, raw in (
        ("data_dir", data_dir),
        ("sqlite_path", sqlite_path),
        ("vector_dir", vector_dir),
    ):
        parts = Path(raw).parts
        for i in range(len(parts) - 1):
            if parts[i] == "backend" and parts[i + 1] == "backend":
                warnings.append(
                    f"{label}={raw!r} looks like a ghost path (backend/backend). "
                    "Leave DATA_DIR/SQLITE_PATH/VECTOR_DIR blank in .env to use repo-root defaults."
                )
                break
    return warnings


class Settings(BaseSettings):
    # --- LLM ---
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
    llm_timeout_seconds: int = 60

    # --- Data Storage ---
    data_dir: str = str(BASE_DIR / "backend" / "data")
    sqlite_path: str = ""
    vector_dir: str = ""

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:5174"
    timezone: str = "Asia/Shanghai"
    """System timezone for cron schedules and time-sensitive product logic."""

    # --- Auth ---
    auth_token: str = ""
    """API Bearer token。未设置则认证关闭，启动时 logger.warning 提示。"""

    allow_no_auth_on_exposed: bool = False
    """允许在公网暴露时无认证运行。仅在明确了解安全风险时设为 true。"""

    trust_proxy_headers: bool = False
    """信任反向代理头（X-Forwarded-For）。仅在部署于受信任的反代（nginx/Caddy/Cloudflare）
    之后时启用，否则外部客户端可伪造 IP 绕过限流。未启用时，限流使用 socket 直接对端 IP。"""

    # --- MCP ---
    mcp_config_path: str = str(BASE_DIR / "backend" / "mcp_config.json")
    """Main MCP config (committed). Holds shared/builtin MCP server registrations."""
    mcp_local_config_path: str = str(BASE_DIR / "backend" / "mcp_config.local.json")
    """Optional personal MCP config (gitignored). ``external_servers`` entries here
    are merged on top of mcp_config.json (by ``name``), letting you add private
    MCPs (TAPD, Jira, internal tools) without touching the shared config.
    File does not need to exist; absence is silently ignored."""
    capability_policy_path: str = str(BASE_DIR / "backend" / "capability_policy.json")
    mcp_external_enabled: bool = True
    """Enable external MCP mesh. Set false to use builtin tools only."""
    builtin_tools_enabled: str = "*"
    """Comma-separated MCP server names to load, or * for all in mcp_config.json."""
    builtin_tool_categories: str = ""
    """Comma-separated advanced builtin CATEGORIES to enable *in addition to*
    the core set (time, filesystem, web, calendar, email, shell, git, goals).
    Empty = core only. Opt-in: telegram, computer_use, voice, clipboard_ocr."""

    # External MCP credentials (optional — servers skip connect when required keys missing)
    brave_api_key: str = ""
    context7_api_key: str = ""
    github_personal_access_token: str = ""
    tavily_api_key: str = ""
    notion_token: str = ""

    # TAPD (Tencent Agile Product Development) — personal access token auth.
    # Get one at https://www.tapd.cn/company/my_tokens. Empty = TAPD MCP server
    # stays dormant (skip-connect), no errors. Workspace ID/Nickname are optional
    # but recommended so you can omit them per-call.
    tapd_access_token: str = ""
    tapd_default_workspace_id: str = ""
    tapd_nick_name: str = ""

    # --- Voice (TTS/STT) — requires an OpenAI-compatible audio endpoint ---
    voice_base_url: str = ""
    """Audio API base URL (e.g. https://api.openai.com/v1). Empty disables voice tools.
    Do not point this at chat-only providers (DeepSeek etc.) — they lack tts/whisper."""
    voice_api_key: str = ""
    """API key for voice endpoint. Falls back to LLM_API_KEY when empty."""
    voice_tts_model: str = "tts-1"
    voice_stt_model: str = "whisper-1"

    # --- Memory ---
    memory_extractor: str = "ollama"
    sensitive_ops_local: bool = True
    execution_shadow_compare: bool = False
    """When True, Scheduler verifies handler_executions projection after each emit (debug)."""

    # --- Filesystem (agent coding) ---
    filesystem_allowed_dirs: str = ""
    """Comma-separated allowed roots for read/write tools. Default: project root. Requires backend restart."""
    filesystem_protected_paths: str = ""
    """Extra comma-separated paths appended to default governance write blocklist. Requires backend restart."""

    # --- Shell (agent coding) ---
    shell_extra_commands: str = ""
    """Comma-separated high-risk commands (rm, chmod, ssh, gpg, brew, apt, …) to enable on top of the safe default whitelist. Leave empty for the hardened default. Requires backend restart."""
    shell_allowed_cwd: str = ""
    """Comma-separated directories the shell tool may run commands in. Default: project root. Requires backend restart."""

    # --- Conversation ---
    max_recent_messages: int = 50
    max_tool_iterations: int = 10
    tool_timeout_seconds: int = 30
    total_tool_loop_timeout: int = 300
    # Hard ceiling on cumulative prompt tokens within one chat turn. When the
    # running total crosses this threshold the loop stops even if iterations
    # remain, preventing runaway cost from long tool chains.
    max_tool_loop_prompt_tokens: int = 100_000
    # Empty-stream retry (complete_text_only) soft timeout in seconds.
    complete_text_only_timeout: float = 45.0

    # --- submit_command timeouts (per call site) ---
    # submit_command emits an event and awaits a matching *Completed event.
    # Each named timeout controls how long the await blocks before returning
    # {"error": "timeout"}. Tune per call site — short for interactive paths
    # (chat / approval), long for background work (inbox, plan execution).
    submit_command_timeout_chat: float = 60.0
    submit_command_timeout_approval: float = 60.0
    submit_command_timeout_background_task: float = 300.0
    submit_command_timeout_inbox: float = 300.0

    # --- Multi-Agent Runtime ---
    # The legacy AgentOrchestrator has been removed (M3 single-track).
    # AgentManager is always active via api/tasks.py.

    # --- Optional LLM fallback providers ---
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:7b"

    # --- Email (Gmail IMAP/SMTP) ---
    email_imap_host: str = "imap.gmail.com"
    email_smtp_host: str = "smtp.gmail.com"
    email_smtp_port: int = 465
    email_user: str = ""
    email_pass: str = ""

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    model_config = {
        "env_file": str(BASE_DIR / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        # Resolve relative paths after defaults are set
        "env_prefix": "",
    }

    def model_post_init(self, _context) -> None:
        """Resolve relative defaults that depend on other fields."""
        if not self.data_dir.strip():
            self.data_dir = str(BASE_DIR / "backend" / "data")
        self.data_dir = resolve_project_path(self.data_dir)
        if self.sqlite_path:
            self.sqlite_path = resolve_project_path(self.sqlite_path)
        else:
            self.sqlite_path = str(Path(self.data_dir) / "personal_ai.db")
        if self.vector_dir:
            self.vector_dir = resolve_project_path(self.vector_dir)
        else:
            self.vector_dir = str(Path(self.data_dir) / "vectors")
        self.mcp_config_path = resolve_project_path(self.mcp_config_path)
        if self.mcp_local_config_path:
            self.mcp_local_config_path = resolve_project_path(self.mcp_local_config_path)
        self.capability_policy_path = resolve_project_path(self.capability_policy_path)


settings = Settings()


def reset_settings() -> None:
    """Re-create the global settings instance from current environment variables.

    Call this in tests after monkeypatching env vars to get a fresh Settings
    object that picks up the new values.  Eliminates the need for
    importlib.reload().
    """
    global settings
    settings = Settings()


# Ensure data directories exist
Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
Path(settings.vector_dir).mkdir(parents=True, exist_ok=True)

for _warn in validate_storage_paths(
    settings.data_dir, settings.sqlite_path, settings.vector_dir
):
    logger.warning("Storage path: %s", _warn)
logger.info(
    "Storage paths — data_dir=%s sqlite=%s vectors=%s",
    settings.data_dir,
    settings.sqlite_path,
    settings.vector_dir,
)
