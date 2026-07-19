"""Unit tests for Voice MCP server (import-safe, no API key needed)."""
import json

import pytest

from app.core.harness.builtin_tools.voice import VoiceServer


class TestVoiceServer:
    def test_init(self):
        s = VoiceServer()
        assert s._client is None

    @pytest.mark.asyncio
    async def test_tts_not_configured(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.harness.builtin_tools.voice.settings.voice_base_url",
            "",
        )
        s = VoiceServer()
        result = json.loads(await s.tts("hello world"))
        assert result["status"] == "error"
        assert "VOICE_BASE_URL" in result["error"]

    @pytest.mark.asyncio
    async def test_tts_empty_text(self):
        s = VoiceServer()
        result = json.loads(await s.tts(""))
        assert result["status"] == "error"
        assert "empty" in result.get("error", "").lower() or "too long" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_tts_too_long(self):
        s = VoiceServer()
        result = json.loads(await s.tts("x" * 4097))
        assert result["status"] == "error"
        assert "too long" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_stt_not_configured(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.harness.builtin_tools.voice.settings.voice_base_url",
            "",
        )
        s = VoiceServer()
        result = json.loads(await s.stt("dGVzdA=="))
        assert result["status"] == "error"
        assert "VOICE_BASE_URL" in result["error"]

    def test_server_singleton(self):
        from app.core.harness.builtin_tools.voice import voice_server
        assert isinstance(voice_server, VoiceServer)
