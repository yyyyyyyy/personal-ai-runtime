"""Egress audit gate — emit failure must not block LLM path."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.runtime.egress.egress_gate import audit_llm_egress, classify_llm_payload


def test_classify_general():
    out = classify_llm_payload([{"role": "user", "content": "hello"}])
    assert out["categories"] == ["general"]


def test_audit_llm_egress_swallows_emit_failure(monkeypatch):
    broken = MagicMock()
    broken.emit_event.side_effect = RuntimeError("kernel down")
    monkeypatch.setattr(
        "app.core.runtime.egress.egress_gate.kernel_instance.kernel",
        broken,
    )
    messages = [{"role": "user", "content": "hi"}]
    out, audit = audit_llm_egress(messages, purpose="chat")
    assert out is messages
    assert audit["emit_failed"] is True
    assert audit["purpose"] == "chat"


def test_audit_llm_egress_success(monkeypatch):
    k = MagicMock()
    monkeypatch.setattr(
        "app.core.runtime.egress.egress_gate.kernel_instance.kernel",
        k,
    )
    messages = [{"role": "user", "content": "memory_id: abc"}]
    out, audit = audit_llm_egress(messages, purpose="chat")
    assert out == messages
    assert "memory_context" in audit["classification"]["categories"]
    assert "emit_failed" not in audit
    k.emit_event.assert_called_once()
