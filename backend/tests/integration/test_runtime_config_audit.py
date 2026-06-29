"""Integration tests for D2 closure: AppConfigChanged audit events in event_log."""

import pytest


class TestAppConfigAudit:
    """Verify AppConfigChanged events appear in event_log after config updates."""

    def test_update_llm_config_emits_audit_event(self, isolated_kernel, monkeypatch):
        kernel, db = isolated_kernel

        # Ensure _cache is cleared so _load_raw returns defaults
        monkeypatch.setattr(
            "app.core.runtime.runtime_config._cache",
            None,
        )

        from app.core.runtime.runtime_config import RuntimeConfig

        config = RuntimeConfig()

        # Update LLM config via the providers list structure
        result = config.update_llm_config({
            "default_provider": "test-provider",
            "temperature": 0.8,
            "max_tokens": 4096,
            "providers": [
                {
                    "id": "test-provider",
                    "name": "Test Provider",
                    "type": "openai_compatible",
                    "base_url": "https://api.test.com/v1",
                    "model": "test-model",
                    "api_key": "sk-test-audit-123",
                    "enabled": True,
                }
            ],
        })

        assert result["default_provider"] == "test-provider"
        assert result["temperature"] == 0.8

        # Verify audit event in event_log
        events = kernel.read_events(type="AppConfigChanged")
        llm_events = [e for e in events if e.payload.get("category") == "llm"]
        assert len(llm_events) >= 1, (
            f"Expected at least 1 AppConfigChanged event for llm, got {len(llm_events)}"
        )

        event = llm_events[0]
        assert event.payload["category"] == "llm"
        assert event.aggregate_type == "app_config"
        assert event.aggregate_id == "llm"

    def test_update_email_config_emits_audit_event(self, isolated_kernel, monkeypatch):
        kernel, db = isolated_kernel

        monkeypatch.setattr(
            "app.core.runtime.runtime_config._cache",
            None,
        )

        from app.core.runtime.runtime_config import RuntimeConfig

        config = RuntimeConfig()

        # Update Email config
        result = config.update_email_config({
            "user": "test@test.com",
            "password": "secret-pwd",
            "imap_host": "imap.test.com",
            "smtp_host": "smtp.test.com",
            "smtp_port": 587,
        })

        assert result["user"] == "test@test.com"
        assert result["password"] == "••••••••"
        assert result["imap_host"] == "imap.test.com"

        # Verify audit event in event_log
        events = kernel.read_events(type="AppConfigChanged")
        email_events = [e for e in events if e.payload.get("category") == "email"]
        assert len(email_events) >= 1, (
            f"Expected at least 1 AppConfigChanged event for email, got {len(email_events)}"
        )

        event = email_events[0]
        assert event.payload["category"] == "email"
        assert event.aggregate_type == "app_config"
        assert event.aggregate_id == "email"

    @pytest.mark.asyncio
    async def test_app_config_events_persist_after_reload(self, isolated_kernel, monkeypatch):
        """Verify AppConfigChanged events survive re-read (roundtrip)."""
        kernel, db = isolated_kernel

        monkeypatch.setattr(
            "app.core.runtime.runtime_config._cache",
            None,
        )

        from app.core.runtime.runtime_config import RuntimeConfig

        config = RuntimeConfig()

        # Update LLM config
        config.update_llm_config({
            "default_provider": "roundtrip-provider",
            "providers": [
                {
                    "id": "roundtrip-provider",
                    "name": "Roundtrip",
                    "type": "openai_compatible",
                    "base_url": "https://api.roundtrip.com/v1",
                    "model": "roundtrip-model",
                    "api_key": "sk-roundtrip-test",
                }
            ],
        })

        # Read events via kernel
        first_read = kernel.read_events(type="AppConfigChanged")

        # Read again — events should persist
        second_read = kernel.read_events(type="AppConfigChanged")
        assert len(second_read) >= len(first_read)
        assert len(second_read) >= 1

        # Verify the roundtrip event content
        llm_events = [e for e in second_read if e.payload.get("category") == "llm"]
        assert len(llm_events) >= 1
        event = llm_events[-1]
        assert "updated_at" in event.payload
