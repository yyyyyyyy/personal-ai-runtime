"""Tests for submit_command timeout configuration."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")


def test_default_timeout_values():
    """Default per-call-site timeouts are sensible."""
    from app.config import Settings

    s = Settings()
    assert s.submit_command_timeout_chat == 60.0
    assert s.submit_command_timeout_approval == 60.0
    assert s.submit_command_timeout_background_task == 300.0
    assert s.submit_command_timeout_inbox == 300.0


def test_timeout_values_overridable_via_env(monkeypatch):
    """Env vars override the per-call-site defaults."""
    monkeypatch.setenv("SUBMIT_COMMAND_TIMEOUT_CHAT", "15")
    monkeypatch.setenv("SUBMIT_COMMAND_TIMEOUT_BACKGROUND_TASK", "600")

    from app.config import Settings

    s = Settings()
    assert s.submit_command_timeout_chat == 15.0
    assert s.submit_command_timeout_background_task == 600.0
    # Unset ones keep defaults
    assert s.submit_command_timeout_approval == 60.0
    assert s.submit_command_timeout_inbox == 300.0


def test_chat_endpoint_uses_configured_timeout():
    """Smoke check: chat.py module references the config field, not a literal."""
    import inspect

    from app.api import chat

    src = inspect.getsource(chat)
    assert "submit_command_timeout_approval" in src, \
        "chat.py must source approval timeout from settings, not hardcode"


def test_approvals_endpoint_uses_configured_timeout():
    """approvals.py both resolve paths must use the config field."""
    import inspect

    from app.api import approvals

    src = inspect.getsource(approvals)
    # Must appear at least twice (one per resolve endpoint).
    assert src.count("submit_command_timeout_approval") >= 2


def test_runtime_loop_uses_configured_timeout():
    """runtime_loop background-task path uses config."""
    import inspect

    from app.core.runtime import runtime_loop

    src = inspect.getsource(runtime_loop)
    assert "submit_command_timeout_background_task" in src


def test_inbox_uses_configured_timeout():
    """inbox.py inbox poll path uses config."""
    import inspect

    from app.product import inbox

    src = inspect.getsource(inbox)
    assert "submit_command_timeout_inbox" in src
