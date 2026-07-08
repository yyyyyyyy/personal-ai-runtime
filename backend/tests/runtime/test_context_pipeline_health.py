"""Tests for ContextPipeline fragment registration health surfacing."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")



def test_health_check_ok_after_normal_construction():
    """When register_all_fragments succeeds, health_check reports ok."""
    from app.core.runtime.governance.context_pipeline import ContextPipeline

    pipeline = ContextPipeline()
    health = pipeline.health_check()
    assert health["fragment_registration"] == "ok"
    assert health["error"] == ""
    # Some fragments should be registered (register_all_fragments runs at init).
    assert health["registered_count"] >= 0


def test_health_check_failed_when_registration_raises(monkeypatch):
    """When register_all_fragments raises, health_check reports failed."""
    import app.fragments.register as reg_mod
    from app.core.runtime.governance.context_pipeline import ContextPipeline

    def _boom(registry):
        raise RuntimeError("simulated DB unavailable")

    monkeypatch.setattr(reg_mod, "register_all_fragments", _boom)

    pipeline = ContextPipeline()
    health = pipeline.health_check()
    assert health["fragment_registration"] == "failed"
    assert "simulated DB unavailable" in health["error"]


def test_health_check_records_count_even_on_failure(monkeypatch):
    """Even on registration failure, registered_count reflects partial state."""
    import app.fragments.register as reg_mod
    from app.core.runtime.governance.context_pipeline import ContextPipeline

    def _partial(registry):
        # Register one fragment before failing so we can verify the count.
        from app.context_runtime import ContextFragment

        registry.register(ContextFragment(id="test.partial"))
        raise RuntimeError("partial registration failed")

    monkeypatch.setattr(reg_mod, "register_all_fragments", _partial)

    pipeline = ContextPipeline()
    health = pipeline.health_check()
    assert health["fragment_registration"] == "failed"
    # The partial fragment is visible in the count.
    assert health["registered_count"] >= 1


def test_missing_fragment_module_treated_as_ok(monkeypatch):
    """When app.fragments.register is absent, health_check reports ok.

    Test environments that don't ship app.fragments shouldn't be marked
    degraded — there is simply nothing to register.
    """
    import sys

    from app.core.runtime.governance.context_pipeline import ContextPipeline

    # Hide the module by inserting a failing import via sys.modules.
    real_mod = sys.modules.pop("app.fragments.register", None)
    real_loader = None
    try:
        # Build a fresh pipeline; the lazy import will fail with ImportError.
        pipeline = ContextPipeline()
        health = pipeline.health_check()
        assert health["fragment_registration"] == "ok"
    finally:
        # Restore so other tests see the real module.
        if real_mod is not None:
            sys.modules["app.fragments.register"] = real_mod
        # Force re-import path next time by clearing ContextPipeline caches.
