"""Multi-LLM Router — supports multiple LLM providers with fallback.

Allows configuring multiple LLM providers and automatically switches
when the primary provider fails. Configuration comes from runtime_config
with .env as initial seed.
"""

from dataclasses import dataclass

from openai import AsyncOpenAI

from app.core.runtime.runtime_config import effective_api_key, runtime_config


@dataclass
class LLMProvider:
    """Configuration for a single LLM provider."""

    name: str
    api_key: str
    base_url: str
    model: str
    provider_type: str = "openai_compatible"
    is_default: bool = False


class LLMRouter:
    """Routes LLM requests to the appropriate provider with fallback."""

    def __init__(self):
        self.providers: list[LLMProvider] = []
        self._clients: dict[str, AsyncOpenAI] = {}
        self._load_providers()

    def _resolve_api_key(self, provider: dict) -> str:
        return effective_api_key(provider)

    def _load_providers(self):
        """Load providers from runtime_config."""
        llm = runtime_config.get_llm_config(masked=False)
        default_id = llm.get("default_provider", "deepseek")
        self.providers = []
        self._clients = {}

        for item in llm.get("providers", []):
            if not item.get("enabled", True):
                continue
            api_key = self._resolve_api_key(item)
            self.providers.append(
                LLMProvider(
                    name=item["id"],
                    api_key=api_key,
                    base_url=item.get("base_url", ""),
                    model=item.get("model", ""),
                    provider_type=item.get("type", "openai_compatible"),
                    is_default=item["id"] == default_id,
                )
            )

        if self.providers and not any(p.is_default for p in self.providers):
            self.providers[0].is_default = True

    def reload(self):
        """Reload providers after runtime config changes."""
        self._load_providers()

    def get_client(self, provider_name: str | None = None) -> tuple[AsyncOpenAI, LLMProvider]:
        """Get a client for the specified provider, or the default one."""
        if provider_name:
            for p in self.providers:
                if p.name == provider_name:
                    if p.name not in self._clients:
                        self._clients[p.name] = AsyncOpenAI(api_key=p.api_key, base_url=p.base_url)
                    return self._clients[p.name], p

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

    def _provider_available(self, provider: LLMProvider) -> bool:
        if provider.provider_type == "ollama":
            return bool(provider.base_url)
        return bool(provider.api_key)

    def list_providers(self) -> list[dict]:
        """List all configured providers with availability."""
        return [
            {
                "name": p.name,
                "model": p.model,
                "type": p.provider_type,
                "is_default": p.is_default,
                "available": self._provider_available(p),
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
