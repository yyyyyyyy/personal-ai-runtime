"""Voice MCP Server — text-to-speech (TTS) and speech-to-text (STT).

Uses OpenAI-compatible API for both. Falls back gracefully when API key is missing.
"""

from __future__ import annotations

import json
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class VoiceServer:
    """Text-to-speech and speech-to-text via OpenAI-compatible API."""

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=settings.llm_api_key,
                    base_url=getattr(settings, 'llm_base_url', 'https://api.deepseek.com/v1'),
                )
            except Exception:
                return None
        return self._client

    def tts(self, text: str, voice: str = "alloy") -> str:
        """Generate speech audio from text. Returns base64-encoded MP3.

        Args:
            text: The text to convert to speech.
            voice: Voice style: alloy, echo, fable, onyx, nova, shimmer.
        """
        client = self._get_client()
        if not client:
            return json.dumps({"status": "error", "error": "LLM client not available"})

        if not text or len(text) > 4096:
            return json.dumps({"status": "error", "error": "Text too long (max 4096 chars)"})

        try:
            import asyncio
            return asyncio.run(self._tts_async(client, text, voice))
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    async def _tts_async(self, client, text: str, voice: str) -> str:
        resp = await client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
        )
        import base64
        audio = base64.b64encode(resp.content).decode("utf-8")
        return json.dumps({
            "status": "ok",
            "audio_base64": audio,
            "format": "mp3",
            "length_chars": len(text),
            "voice": voice,
        })

    def stt(self, audio_base64: str, language: str = "zh") -> str:
        """Transcribe speech audio to text. Returns the transcript.

        Args:
            audio_base64: Base64-encoded audio bytes.
            language: Language code (zh, en, ja, etc).
        """
        client = self._get_client()
        if not client:
            return json.dumps({"status": "error", "error": "LLM client not available"})

        try:
            import asyncio
            return asyncio.run(self._stt_async(client, audio_base64, language))
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    async def _stt_async(self, client, audio_base64: str, language: str) -> str:
        import base64
        import tempfile
        from pathlib import Path

        audio_bytes = base64.b64decode(audio_base64)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)

        try:
            with open(tmp_path, "rb") as f:
                resp = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language=language,
                )
            return json.dumps({
                "status": "ok",
                "text": resp.text,
                "language": language,
            })
        finally:
            tmp_path.unlink()


voice_server = VoiceServer()
