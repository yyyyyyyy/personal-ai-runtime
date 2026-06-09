"""LLM router fallback clients."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")


def test_fallback_clients_excludes_default():
    from app.core.agents.llm_router import llm_router

    fallbacks = llm_router.get_fallback_clients()
    for _, provider in fallbacks:
        assert not provider.is_default
