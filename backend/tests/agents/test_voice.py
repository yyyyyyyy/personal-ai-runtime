"""Unit tests for Voice MCP server (import-safe, no API key needed)."""
import json

from app.core.harness.builtin_tools.voice import VoiceServer


class TestVoiceServer:
    def test_init(self):
        s = VoiceServer()
        assert s._client is None

    def test_tts_no_api_key(self):
        s = VoiceServer()
        result = json.loads(s.tts("hello world"))
        assert result["status"] == "error"

    def test_tts_empty_text(self):
        s = VoiceServer()
        result = json.loads(s.tts(""))
        assert result["status"] == "error"
        assert "Text too long" in result.get("error", "")

    def test_tts_too_long(self):
        s = VoiceServer()
        result = json.loads(s.tts("x" * 4097))
        assert result["status"] == "error"
        assert "too long" in result.get("error", "").lower()

    def test_tts_different_voices(self):
        s = VoiceServer()
        for voice in ("alloy", "echo", "fable", "onyx", "nova", "shimmer"):
            result = json.loads(s.tts("test", voice=voice))
            assert result["status"] == "error"  # no API key, but format is valid

    def test_stt_no_api_key(self):
        s = VoiceServer()
        result = json.loads(s.stt("dGVzdA=="))  # "test" in base64
        assert result["status"] == "error"

    def test_stt_different_languages(self):
        s = VoiceServer()
        for lang in ("zh", "en", "ja"):
            result = json.loads(s.stt("dGVzdA==", language=lang))
            assert result["status"] == "error"

    def test_server_singleton(self):
        from app.core.harness.builtin_tools.voice import voice_server
        assert isinstance(voice_server, VoiceServer)
