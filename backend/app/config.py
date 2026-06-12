"""Application configuration management using pydantic-settings."""

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings(BaseSettings):
    # --- LLM ---
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096

    # --- Data Storage ---
    data_dir: str = str(BASE_DIR / "backend" / "data")
    sqlite_path: str = ""
    vector_dir: str = ""

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # --- Auth ---
    auth_token: str = ""
    """API 认证 Token。若未设置，启动时自动生成随机 Token 并打印到控制台。"""

    # --- MCP ---
    mcp_config_path: str = str(BASE_DIR / "backend" / "mcp_config.json")
    capability_policy_path: str = str(BASE_DIR / "backend" / "capability_policy.json")

    # --- Memory ---
    memory_extractor: str = "ollama"
    sensitive_ops_local: bool = False

    # --- Conversation ---
    max_recent_messages: int = 50
    max_tool_iterations: int = 10
    tool_timeout_seconds: int = 30
    total_tool_loop_timeout: int = 120

    # --- Misc ---
    review_narrative_llm_enabled: bool = True

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
        if not self.sqlite_path:
            self.sqlite_path = str(Path(self.data_dir) / "personal_ai.db")
        if not self.vector_dir:
            self.vector_dir = str(Path(self.data_dir) / "vectors")


settings = Settings()

# Ensure data directories exist
Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
Path(settings.vector_dir).mkdir(parents=True, exist_ok=True)
