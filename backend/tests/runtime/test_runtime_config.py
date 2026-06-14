"""Tests for runtime configuration storage."""

import json

import pytest

from app.core.runtime.runtime_config import _MASKED_SECRET, invalidate_runtime_config_cache, runtime_config


@pytest.fixture
def isolated_runtime_config(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import reset_settings

    reset_settings()
    invalidate_runtime_config_cache()
    config_file = tmp_path / "runtime_config.json"
    if config_file.exists():
        config_file.unlink()
    yield tmp_path
    if config_file.exists():
        config_file.unlink()


def test_default_llm_config_from_env(isolated_runtime_config, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    from app.config import reset_settings

    reset_settings()
    from app.core.runtime import runtime_config as rc_mod

    rc_mod.runtime_config = rc_mod.RuntimeConfig()
    rc_mod.invalidate_runtime_config_cache()
    llm = rc_mod.runtime_config.get_llm_config(masked=False)
    assert llm["default_provider"] == "deepseek"
    assert any(p["id"] == "deepseek" for p in llm["providers"])


def test_update_llm_masks_api_key(isolated_runtime_config):
    from app.core.runtime import runtime_config as rc_mod

    rc_mod.runtime_config = rc_mod.RuntimeConfig()
    rc_mod.runtime_config.update_llm_config({
        "providers": [{
            "id": "deepseek",
            "name": "DeepSeek",
            "type": "openai_compatible",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_key": "secret-key-123",
            "enabled": True,
        }],
    })
    masked = rc_mod.runtime_config.get_llm_config(masked=True)
    assert masked["providers"][0]["api_key"] == _MASKED_SECRET
    assert masked["providers"][0]["has_api_key"] is True


def test_update_llm_preserves_key_when_masked(isolated_runtime_config):
    from app.core.runtime import runtime_config as rc_mod

    rc_mod.runtime_config = rc_mod.RuntimeConfig()
    rc_mod.runtime_config.update_llm_config({
        "providers": [{
            "id": "deepseek",
            "name": "DeepSeek",
            "type": "openai_compatible",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_key": "keep-this-key",
            "enabled": True,
        }],
    })
    rc_mod.runtime_config.update_llm_config({
        "providers": [{
            "id": "deepseek",
            "name": "DeepSeek",
            "type": "openai_compatible",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_key": _MASKED_SECRET,
            "enabled": True,
        }],
    })
    raw = rc_mod.runtime_config.get_llm_config(masked=False)
    assert raw["providers"][0]["api_key"] == "keep-this-key"


def test_update_email_config(isolated_runtime_config):
    from app.core.runtime import runtime_config as rc_mod

    rc_mod.runtime_config = rc_mod.RuntimeConfig()
    result = rc_mod.runtime_config.update_email_config({
        "user": "test@gmail.com",
        "password": "app-password",
    })
    assert result["user"] == "test@gmail.com"
    assert result["password"] == _MASKED_SECRET

    creds = rc_mod.runtime_config.get_email_credentials()
    assert creds["user"] == "test@gmail.com"
    assert creds["password"] == "app-password"


def test_effective_api_key_falls_back_to_env(monkeypatch):
    monkeypatch.setattr(
        "app.core.runtime.runtime_config.settings.llm_api_key",
        "real-env-key-from-dotenv",
    )
    from app.core.runtime.runtime_config import effective_api_key

    provider = {
        "id": "deepseek",
        "type": "openai_compatible",
        "api_key": "test-key",
    }
    assert effective_api_key(provider) == "real-env-key-from-dotenv"
    assert effective_api_key({**provider, "api_key": "sk-user-key"}) == "sk-user-key"


def test_config_persisted_to_db(isolated_runtime_config):
    from app.core.runtime.runtime_config import RuntimeConfig
    from app.store.database import db

    rc = RuntimeConfig()
    rc.update_email_config({
        "user": "persist@gmail.com",
        "password": "secret",
    })
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT data_json FROM app_settings WHERE category = 'email'"
        ).fetchone()
    assert row is not None
    data = json.loads(row["data_json"])
    assert data["user"] == "persist@gmail.com"
