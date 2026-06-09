"""Application configuration management."""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")

    data_dir: str = os.getenv("DATA_DIR", str(BASE_DIR / "backend" / "data"))
    sqlite_path: str = os.getenv("SQLITE_PATH", str(Path(data_dir) / "personal_ai.db"))
    vector_dir: str = os.getenv("VECTOR_DIR", str(Path(data_dir) / "vectors"))

    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:5173")

    mcp_config_path: str = os.getenv(
        "MCP_CONFIG_PATH", str(BASE_DIR / "backend" / "mcp_config.json")
    )

    # Conversation settings
    max_recent_messages: int = 50  # sliding window size
    max_tool_iterations: int = 5
    tool_timeout_seconds: int = 30
    total_tool_loop_timeout: int = 120

    # LLM settings
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096


settings = Settings()

# Ensure data directories exist
Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
Path(settings.vector_dir).mkdir(parents=True, exist_ok=True)
