"""Unit tests for Voice MCP server (import-safe, no API key needed)."""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

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

    @pytest.mark.asyncio
    async def test_tts_success_with_mock_client(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.harness.builtin_tools.voice.settings.voice_base_url",
            "https://voice.example/v1",
        )
        monkeypatch.setattr(
            "app.core.harness.builtin_tools.voice.settings.voice_api_key",
            "test-key",
        )
        s = VoiceServer()
        fake_client = SimpleNamespace(
            audio=SimpleNamespace(
                speech=SimpleNamespace(
                    create=AsyncMock(return_value=SimpleNamespace(content=b"mp3-bytes")),
                )
            )
        )
        s._client = fake_client

        result = json.loads(await s.tts("hello", voice="alloy"))
        assert result["status"] == "ok"
        assert result["format"] == "mp3"
        assert result["voice"] == "alloy"
        assert result["audio_base64"] == base64.b64encode(b"mp3-bytes").decode("utf-8")
        fake_client.audio.speech.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stt_success_with_mock_client(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.harness.builtin_tools.voice.settings.voice_base_url",
            "https://voice.example/v1",
        )
        monkeypatch.setattr(
            "app.core.harness.builtin_tools.voice.settings.voice_api_key",
            "test-key",
        )
        s = VoiceServer()
        fake_client = SimpleNamespace(
            audio=SimpleNamespace(
                transcriptions=SimpleNamespace(
                    create=AsyncMock(return_value=SimpleNamespace(text="你好世界")),
                )
            )
        )
        s._client = fake_client

        audio_b64 = base64.b64encode(b"fake-wav").decode("utf-8")
        result = json.loads(await s.stt(audio_b64, language="zh"))
        assert result["status"] == "ok"
        assert result["text"] == "你好世界"
        assert result["language"] == "zh"
        fake_client.audio.transcriptions.create.assert_awaited_once()
