"""LLM router fallback clients."""

def test_fallback_clients_excludes_default():
    from app.core.agents.llm_failover import llm_router

    fallbacks = llm_router.get_fallback_clients()
    for _, provider in fallbacks:
        assert not provider.is_default
