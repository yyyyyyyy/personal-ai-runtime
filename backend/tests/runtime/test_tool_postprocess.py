"""Tests for tool post-processing registry."""

import json

from app.core.agents.tool_postprocess import (
    build_prompt_hints,
    canned_summary,
    compact_for_llm,
)


def test_compact_inbox_strips_body():
    payload = {
        "count": 1,
        "emails": [{"from": "a@b.com", "subject": "Hi", "date": "2026-01-01", "body": "secret"}],
    }
    out = compact_for_llm("check_inbox", json.dumps(payload))
    data = json.loads(out)
    assert "body" not in data["emails"][0]
    assert data["emails"][0]["index"] == 1


def test_canned_summary_for_inbox_only():
    tool_calls = [{"function_name": "check_inbox", "id": "tc1"}]
    results = [{
        "tool_name": "check_inbox",
        "content": json.dumps({"count": 3, "emails": []}),
    }]
    summary = canned_summary(tool_calls, results)
    assert summary is not None
    assert "3" in summary


def test_prompt_hints_when_tools_available():
    hints = build_prompt_hints({"check_inbox", "read_inbox_email"})
    assert "check_inbox" in hints or "read_inbox_email" in hints
    assert build_prompt_hints(set()) == ""
