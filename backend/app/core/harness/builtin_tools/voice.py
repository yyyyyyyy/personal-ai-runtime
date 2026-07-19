"""Voice MCP Server — text-to-speech (TTS) and speech-to-text (STT).

Requires an OpenAI-compatible *audio* endpoint via ``VOICE_BASE_URL``.
Chat-only providers (e.g. default DeepSeek) are not used — they lack
``tts-1`` / ``whisper-1`` and would fail at call time.
"""

from __future__ import annotations

import base64
import json
import logging
import tempfile
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class VoiceServer:
    """Async TTS/STT via a dedicated OpenAI-compatible audio API."""

    def __init__(self) -> None:
        self._client = None

    def _configured(self) -> str | None:
        """Return an error message if voice is not configured, else None."""
        if not settings.voice_base_url.strip():
            return (
                "Voice not configured: set VOICE_BASE_URL to an OpenAI-compatible "
                "audio endpoint (e.g. https://api.openai.com/v1)"
            )
        key = (settings.voice_api_key or settings.llm_api_key or "").strip()
        if not key:
            return "Voice not configured: set VOICE_API_KEY or LLM_API_KEY"
        return None

    def _get_client(self):
        err = self._configured()
        if err:
            return None, err
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(
                    api_key=(settings.voice_api_key or settings.llm_api_key).strip(),
                    base_url=settings.voice_base_url.strip(),
                    timeout=float(settings.llm_timeout_seconds),
                    max_retries=3,
                )
            except Exception as exc:
                return None, f"LLM client not available: {exc}"
        return self._client, None

    async def tts(self, text: str, voice: str = "alloy") -> str:
        """Generate speech audio from text. Returns base64-encoded MP3."""
        if not text or len(text) > 4096:
            return json.dumps({
                "status": "error",
                "error": "Text empty or too long (max 4096 chars)",
            })

        client, err = self._get_client()
        if err or client is None:
            return json.dumps({"status": "error", "error": err or "LLM client not available"})

        try:
            resp = await client.audio.speech.create(
                model=settings.voice_tts_model,
                voice=voice,
                input=text,
            )
            audio = base64.b64encode(resp.content).decode("utf-8")
            return json.dumps({
                "status": "ok",
                "audio_base64": audio,
                "format": "mp3",
                "length_chars": len(text),
                "voice": voice,
            })
        except Exception as e:
            logger.exception("voice_tts failed")
            return json.dumps({"status": "error", "error": str(e)})

    async def stt(self, audio_base64: str, language: str = "zh") -> str:
        """Transcribe speech audio to text."""
        client, err = self._get_client()
        if err or client is None:
            return json.dumps({"status": "error", "error": err or "LLM client not available"})

        tmp_path: Path | None = None
        try:
            audio_bytes = base64.b64decode(audio_base64)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = Path(tmp.name)

            with open(tmp_path, "rb") as f:
                resp = await client.audio.transcriptions.create(
                    model=settings.voice_stt_model,
                    file=f,
                    language=language,
                )
            return json.dumps({
                "status": "ok",
                "text": resp.text,
                "language": language,
            })
        except Exception as e:
            logger.exception("voice_stt failed")
            return json.dumps({"status": "error", "error": str(e)})
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)


voice_server = VoiceServer()
