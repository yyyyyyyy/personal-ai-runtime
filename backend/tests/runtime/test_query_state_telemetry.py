"""Kernel query_state filters for governed telemetry tables."""

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT / "backend"))

import pytest

from app.core.runtime.kernel.kernel import Kernel

@pytest.fixture
def kernel(isolated_kernel):
    k, _db = isolated_kernel
    return k

def test_llm_calls_since_days_and_offset(kernel):
    for i in range(3):
        kernel.emit_event(
            "LLMCallRecorded",
            "llm_call",
            f"llm_{i}",
            payload={
                "provider": "test",
                "model": "m",
                "prompt_tokens": i,
                "completion_tokens": 1,
                "cost": 0.0,
                "latency_ms": 10,
                "success": True,
            },
            actor="test",
        )

    all_rows = kernel.query_state("llm_calls", limit=10)
    assert len(all_rows) == 3

    page = kernel.query_state("llm_calls", limit=2, offset=1)
    assert len(page) == 2

    recent = kernel.query_state("llm_calls", since_days=7, limit=10)
    assert len(recent) == 3

def test_llm_calls_purpose_filter(kernel):
    kernel.emit_event(
        "LLMCallRecorded",
        "llm_call",
        "llm_chat",
        payload={
            "provider": "test",
            "model": "m",
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "cost": 0.0,
            "latency_ms": 1,
            "success": True,
            "purpose": "chat",
        },
        actor="test",
    )
    kernel.emit_event(
        "LLMCallRecorded",
        "llm_call",
        "llm_mem",
        payload={
            "provider": "ollama",
            "model": "qwen",
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "cost": 0.0,
            "latency_ms": 1,
            "success": True,
            "purpose": "memory_extract",
        },
        actor="test",
    )

    rows = kernel.query_state("llm_calls", purpose="memory_extract", limit=10)
    assert len(rows) == 1
    assert rows[0]["purpose"] == "memory_extract"

def test_tool_calls_tool_name_filter(kernel):
    kernel.emit_event(
        "CapabilityInvoked",
        "capability",
        "cap_a",
        payload={"name": "web_search", "success": True, "latency_ms": 5},
        actor="test",
    )
    kernel.emit_event(
        "CapabilityInvoked",
        "capability",
        "cap_b",
        payload={"name": "read_file", "success": True, "latency_ms": 5},
        actor="test",
    )

    rows = kernel.query_state("tool_calls", tool_name="web_search", limit=10)
    assert len(rows) == 1
    assert rows[0]["tool_name"] == "web_search"
