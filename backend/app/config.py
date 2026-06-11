"""Application configuration management."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

# Disable ChromaDB internal telemetry to avoid posthog compatibility issues
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

# Suppress tokenizers warning from ChromaDB embedding function
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


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
    capability_policy_path: str = os.getenv(
        "CAPABILITY_POLICY_PATH", str(BASE_DIR / "backend" / "capability_policy.json")
    )
    trajectory_registry_path: str = os.getenv(
        "TRAJECTORY_REGISTRY_PATH", str(BASE_DIR / "backend" / "trajectory_registry.yaml")
    )
    identity_surfaces_path: str = os.getenv(
        "IDENTITY_SURFACES_PATH", str(BASE_DIR / "backend" / "identity_surfaces.yaml")
    )
    agency_surfaces_path: str = os.getenv(
        "AGENCY_SURFACES_PATH", str(BASE_DIR / "backend" / "agency_surfaces.yaml")
    )
    memory_extractor: str = os.getenv("MEMORY_EXTRACTOR", "ollama")  # ollama | cloud
    sensitive_ops_local: bool = os.getenv("SENSITIVE_OPS_LOCAL", "false").lower() == "true"

    # Conversation settings
    max_recent_messages: int = 50  # sliding window size
    max_tool_iterations: int = int(os.getenv("MAX_TOOL_ITERATIONS", "10"))
    tool_timeout_seconds: int = 30
    total_tool_loop_timeout: int = 120

    # LLM settings
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
    review_narrative_llm_enabled: bool = (
        os.getenv("REVIEW_NARRATIVE_LLM_ENABLED", "false").lower() == "true"
    )


settings = Settings()

# Ensure data directories exist
Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
Path(settings.vector_dir).mkdir(parents=True, exist_ok=True)
