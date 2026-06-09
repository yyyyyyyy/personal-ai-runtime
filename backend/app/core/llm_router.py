"""Multi-LLM Router — supports multiple LLM providers with fallback.

Allows configuring multiple LLM providers and automatically switches
when the primary provider fails.
"""

from dataclasses import dataclass, field
from typing import Any
from openai import AsyncOpenAI

from app.config import settings


@dataclass
class LLMProvider:
    """Configuration for a single LLM provider."""

    name: str
    api_key: str
    base_url: str
    model: str
    is_default: bool = False


class LLMRouter:
    """Routes LLM requests to the appropriate provider with fallback."""

    def __init__(self):
        self.providers: list[LLMProvider] = []
        self._load_providers()
        self._clients: dict[str, AsyncOpenAI] = {}

    def _load_providers(self):
        """Load providers from settings. Default provider comes from .env."""
        self.providers = [
            LLMProvider(
                name="deepseek",
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                model=settings.llm_model,
                is_default=True,
            )
        ]

        # Optional secondary providers from env
        import os
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if openai_key:
            self.providers.append(
                LLMProvider(
                    name="openai",
                    api_key=openai_key,
                    base_url="https://api.openai.com/v1",
                    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                )
            )

        claude_key = os.getenv("ANTHROPIC_API_KEY", "")
        if claude_key:
            # Claude via OpenAI-compatible proxy is common
            claude_base = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
            self.providers.append(
                LLMProvider(
                    name="claude",
                    api_key=claude_key,
                    base_url=claude_base,
                    model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
                )
            )

        ollama_url = os.getenv("OLLAMA_BASE_URL", "")
        if ollama_url:
            self.providers.append(
                LLMProvider(
                    name="ollama",
                    api_key="ollama",
                    base_url=ollama_url,
                    model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
                )
            )

    def get_client(self, provider_name: str | None = None) -> tuple[AsyncOpenAI, LLMProvider]:
        """Get a client for the specified provider, or the default one."""
        if provider_name:
            for p in self.providers:
                if p.name == provider_name:
                    if p.name not in self._clients:
                        self._clients[p.name] = AsyncOpenAI(api_key=p.api_key, base_url=p.base_url)
                    return self._clients[p.name], p

        # Return default
        for p in self.providers:
            if p.is_default:
                if p.name not in self._clients:
                    self._clients[p.name] = AsyncOpenAI(api_key=p.api_key, base_url=p.base_url)
                return self._clients[p.name], p

        raise RuntimeError("No LLM provider configured")

    def get_fallback_clients(self) -> list[tuple[AsyncOpenAI, LLMProvider]]:
        """Get all non-default clients for fallback."""
        result = []
        for p in self.providers:
            if not p.is_default:
                if p.name not in self._clients:
                    self._clients[p.name] = AsyncOpenAI(api_key=p.api_key, base_url=p.base_url)
                result.append((self._clients[p.name], p))
        return result

    def list_providers(self) -> list[dict]:
        """List all configured providers."""
        return [
            {
                "name": p.name,
                "model": p.model,
                "is_default": p.is_default,
            }
            for p in self.providers
        ]

    def get_default_model(self) -> str:
        """Get the default model name."""
        for p in self.providers:
            if p.is_default:
                return p.model
        return "deepseek-chat"


# Global singleton
llm_router = LLMRouter()
