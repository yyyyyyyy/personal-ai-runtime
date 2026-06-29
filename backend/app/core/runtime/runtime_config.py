"""Runtime configuration — LLM and email settings persisted in SQLite.

Env vars seed defaults on first load; UI edits are stored in app_settings table.
Legacy runtime_config.json is migrated automatically on first read.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.runtime import kernel_instance as _kernel_module
from app.store.database import db

logger = logging.getLogger(__name__)

_CONFIG_FILENAME = "runtime_config.json"
_lock = threading.Lock()
_MASKED_SECRET = "••••••••"
_cache: dict[str, Any] | None = None

# Provider type → connection semantics (all use OpenAI SDK today).
PROVIDER_TYPES = {
    "openai_compatible": {
        "label": "OpenAI 兼容",
        "description": "DeepSeek、OpenAI、Ollama 及各类兼容代理",
        "requires_api_key": True,
    },
    "ollama": {
        "label": "Ollama 本地",
        "description": "本地 Ollama，API Key 可填 ollama",
        "requires_api_key": False,
    },
}

PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "deepseek": {
        "name": "DeepSeek",
        "type": "openai_compatible",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "openai": {
        "name": "OpenAI",
        "type": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "anthropic": {
        "name": "Anthropic (兼容代理)",
        "type": "openai_compatible",
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-sonnet-4-20250514",
    },
    "ollama": {
        "name": "Ollama",
        "type": "ollama",
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5:7b",
    },
}

GMAIL_DEFAULTS = {
    "provider": "gmail",
    "imap_host": "imap.gmail.com",
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 465,
}


def _config_path() -> Path:
    return Path(settings.data_dir) / _CONFIG_FILENAME


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    return _MASKED_SECRET


_PLACEHOLDER_API_KEYS = frozenset({"", "test-key", "keep-this-key", "ollama"})


def _env_api_key_for_provider(provider_id: str) -> str:
    """Read API key from environment for known provider ids."""
    env_map = {
        "deepseek": settings.llm_api_key,
        "openai": os.getenv("OPENAI_API_KEY", ""),
        "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
    }
    return env_map.get(provider_id, "")


def effective_api_key(provider: dict[str, Any]) -> str:
    """Resolve API key: DB value wins, else fall back to .env for known providers."""
    ptype = provider.get("type", "openai_compatible")
    stored = (provider.get("api_key") or "").strip()
    if ptype == "ollama":
        return stored or "ollama"
    if stored and stored not in _PLACEHOLDER_API_KEYS:
        return stored
    env_key = _env_api_key_for_provider(provider.get("id", ""))
    return env_key or stored


def _is_masked(value: str | None) -> bool:
    return value == _MASKED_SECRET or (value or "").startswith("••••")


def _default_llm_from_env() -> dict[str, Any]:
    providers: list[dict[str, Any]] = [
        {
            "id": "deepseek",
            "name": "DeepSeek",
            "type": "openai_compatible",
            "base_url": settings.llm_base_url,
            "model": settings.llm_model,
            "api_key": settings.llm_api_key,
            "enabled": True,
        }
    ]

    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        providers.append({
            "id": "openai",
            "name": "OpenAI",
            "type": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "api_key": openai_key,
            "enabled": True,
        })

    claude_key = os.getenv("ANTHROPIC_API_KEY", "")
    if claude_key:
        providers.append({
            "id": "anthropic",
            "name": "Anthropic",
            "type": "openai_compatible",
            "base_url": os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1"),
            "model": os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
            "api_key": claude_key,
            "enabled": True,
        })

    ollama_url = os.getenv("OLLAMA_BASE_URL", "") or settings.ollama_base_url
    if ollama_url:
        providers.append({
            "id": "ollama",
            "name": "Ollama",
            "type": "ollama",
            "base_url": ollama_url,
            "model": os.getenv("OLLAMA_MODEL", settings.ollama_model),
            "api_key": "ollama",
            "enabled": True,
        })

    return {
        "default_provider": "deepseek",
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "providers": providers,
    }


def _default_email_from_env() -> dict[str, Any]:
    return {
        **GMAIL_DEFAULTS,
        "user": settings.email_user,
        "password": settings.email_pass,
    }


def _defaults() -> dict[str, Any]:
    return {
        "llm": _default_llm_from_env(),
        "email": _default_email_from_env(),
    }


def _read_category(conn, category: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT data_json FROM app_settings WHERE category = ?",
        (category,),
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["data_json"])
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Invalid app_settings JSON for %s: %s", category, exc)
        return None


def _load_from_db() -> dict[str, Any] | None:
    try:
        with db.get_db() as conn:
            llm = _read_category(conn, "llm")
            email = _read_category(conn, "email")
        if llm is None and email is None:
            return None
        defaults = _defaults()
        return {
            "llm": llm if llm is not None else defaults["llm"],
            "email": email if email is not None else defaults["email"],
        }
    except Exception as exc:
        logger.warning("Failed to load app_settings from DB: %s", exc)
        return None


def _load_from_json_file() -> dict[str, Any] | None:
    path = _config_path()
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        defaults = _defaults()
        if "llm" not in data:
            data["llm"] = defaults["llm"]
        if "email" not in data:
            data["email"] = defaults["email"]
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load legacy runtime config: %s", exc)
        return None


def _load_raw(*, force: bool = False) -> dict[str, Any]:
    global _cache
    if _cache is not None and not force:
        return deepcopy(_cache)

    data = _load_from_db()
    if data is not None:
        _cache = deepcopy(data)
        return deepcopy(data)

    legacy = _load_from_json_file()
    if legacy is not None:
        _save_raw(legacy)
        logger.info("Migrated runtime_config.json into app_settings table")
        return deepcopy(_cache)  # type: ignore[arg-type]

    data = _defaults()
    _cache = deepcopy(data)
    return deepcopy(data)


def _save_raw(data: dict[str, Any]) -> None:
    global _cache
    now = datetime.now(UTC).isoformat()
    with db.get_db() as conn:
        for category in ("llm", "email"):
            conn.execute(
                """INSERT INTO app_settings (category, data_json, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(category) DO UPDATE SET
                     data_json = excluded.data_json,
                     updated_at = excluded.updated_at""",
                (category, json.dumps(data[category], ensure_ascii=False), now),
            )
    _cache = deepcopy(data)
    # B2: emit audit event to event_log for config change traceability
    try:
        for category in ("llm", "email"):
            _kernel_module.kernel.emit_event(
                "AppConfigChanged",
                "app_config",
                category,
                payload={
                    "category": category,
                    "updated_at": now,
                },
                actor="user",
            )
    except Exception:
        logger.warning("Failed to emit AppConfigChanged audit event", exc_info=True)


def invalidate_runtime_config_cache() -> None:
    """Clear in-memory cache (tests / forced reload)."""
    global _cache
    _cache = None


class RuntimeConfig:
    """Thread-safe runtime configuration store."""

    @staticmethod
    def _apply_llm_mask(llm: dict[str, Any]) -> dict[str, Any]:
        masked = deepcopy(llm)
        for p in masked.get("providers", []):
            raw_key = effective_api_key(p)
            p["has_api_key"] = bool(raw_key)
            p["api_key"] = _mask_secret(raw_key)
        return masked

    @staticmethod
    def _apply_email_mask(email_cfg: dict[str, Any]) -> dict[str, Any]:
        masked = deepcopy(email_cfg)
        raw_pass = masked.get("password", "")
        masked["configured"] = bool(masked.get("user") and raw_pass)
        masked["password"] = _mask_secret(raw_pass)
        return masked

    def get_llm_config(self, masked: bool = True) -> dict[str, Any]:
        with _lock:
            llm = deepcopy(_load_raw()["llm"])
        if masked:
            return self._apply_llm_mask(llm)
        return llm

    def get_email_config(self, masked: bool = True) -> dict[str, Any]:
        with _lock:
            email_cfg = deepcopy(_load_raw()["email"])
        if masked:
            return self._apply_email_mask(email_cfg)
        return email_cfg

    def get_provider_presets(self) -> dict[str, Any]:
        return {
            "types": PROVIDER_TYPES,
            "presets": PROVIDER_PRESETS,
        }

    def update_llm_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        with _lock:
            raw = _load_raw()
            current = raw["llm"]
            new_llm = deepcopy(current)

            if "default_provider" in payload:
                new_llm["default_provider"] = payload["default_provider"]
            if "temperature" in payload:
                new_llm["temperature"] = float(payload["temperature"])
            if "max_tokens" in payload:
                new_llm["max_tokens"] = int(payload["max_tokens"])

            if "providers" in payload:
                existing_by_id = {p["id"]: p for p in current.get("providers", [])}
                merged: list[dict[str, Any]] = []
                for item in payload["providers"]:
                    pid = item["id"]
                    prev = existing_by_id.get(pid, {})
                    api_key = item.get("api_key", "")
                    if _is_masked(api_key):
                        api_key = prev.get("api_key", "")
                    merged.append({
                        "id": pid,
                        "name": item.get("name") or prev.get("name") or pid,
                        "type": item.get("type") or prev.get("type") or "openai_compatible",
                        "base_url": item.get("base_url") or prev.get("base_url", ""),
                        "model": item.get("model") or prev.get("model", ""),
                        "api_key": api_key,
                        "enabled": item.get("enabled", prev.get("enabled", True)),
                    })
                new_llm["providers"] = merged

            raw["llm"] = new_llm
            _save_raw(raw)
            return self._apply_llm_mask(new_llm)

    def update_email_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        with _lock:
            raw = _load_raw()
            current = raw["email"]
            password = payload.get("password", current.get("password", ""))
            if _is_masked(password):
                password = current.get("password", "")

            raw["email"] = {
                "provider": "gmail",
                "user": payload.get("user", current.get("user", "")),
                "password": password,
                "imap_host": payload.get("imap_host", current.get("imap_host", GMAIL_DEFAULTS["imap_host"])),
                "smtp_host": payload.get("smtp_host", current.get("smtp_host", GMAIL_DEFAULTS["smtp_host"])),
                "smtp_port": int(payload.get("smtp_port", current.get("smtp_port", GMAIL_DEFAULTS["smtp_port"]))),
            }
            _save_raw(raw)
            return self._apply_email_mask(raw["email"])

    def get_provider_credentials(self, provider_id: str | None = None) -> list[dict[str, Any]]:
        """Return enabled providers with unmasked secrets for internal use."""
        llm = self.get_llm_config(masked=False)
        providers = [p for p in llm.get("providers", []) if p.get("enabled", True)]
        if provider_id:
            providers = [p for p in providers if p["id"] == provider_id]
        resolved: list[dict[str, Any]] = []
        for p in providers:
            item = deepcopy(p)
            item["api_key"] = effective_api_key(p)
            resolved.append(item)
        return resolved

    def get_email_credentials(self) -> dict[str, Any]:
        return self.get_email_config(masked=False)

    def get_generation_params(self) -> tuple[float, int]:
        """Return (temperature, max_tokens) from runtime LLM config."""
        llm = self.get_llm_config(masked=False)
        return (
            float(llm.get("temperature", settings.llm_temperature)),
            int(llm.get("max_tokens", settings.llm_max_tokens)),
        )

    def get_prompt(self, key: str) -> str | None:
        """Get a user-customized prompt from app_settings."""
        try:
            with db.get_db() as conn:
                row = conn.execute(
                    "SELECT data_json FROM app_settings WHERE category = ?",
                    (f"prompt_{key}",),
                ).fetchone()
                if row:
                    data = json.loads(row["data_json"])
                    return data.get("content")
        except Exception:
            logger.warning("Failed to load prompt '%s' from DB", key, exc_info=True)
        return None

    def save_prompt(self, key: str, content: str) -> None:
        """Save a user-customized prompt to app_settings."""
        now = datetime.now(UTC).isoformat()
        category = f"prompt_{key}"
        try:
            with db.get_db() as conn:
                conn.execute(
                    """INSERT INTO app_settings (category, data_json, updated_at)
                       VALUES (?, ?, ?)
                       ON CONFLICT(category) DO UPDATE SET
                         data_json = excluded.data_json,
                         updated_at = excluded.updated_at""",
                    (category, json.dumps({"content": content, "key": key}, ensure_ascii=False), now),
                )
            # Invalidate cache to reload prompts
            invalidate_runtime_config_cache()
        except Exception:
            logger.warning("Failed to save prompt '%s' to DB", key, exc_info=True)
            raise


runtime_config = RuntimeConfig()
