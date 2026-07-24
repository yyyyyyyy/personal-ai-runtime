"""Unit tests for _conversation_context_for_correlation (P3 review gap).

Covers the multi-same-name tool_call disambiguation: when an assistant
emitted two ``write_file`` tool calls in the same conversation and only
the first has a matching tool-result, the helper must return the
unanswered one.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.api.approvals import _conversation_context_for_correlation


class _StubKernel:
    def __init__(self, conv_id, messages, chat_events):
        self._conv_id = conv_id
        self._messages = messages
        self._chat_events = chat_events

    def read_events(self, **kwargs):
        # Only called with correlation_id filter in the helper.
        corr = kwargs.get("correlation_id")
        if corr and corr.startswith("chat_") and self._chat_events:
            return [SimpleNamespace(aggregate_id=self._conv_id)]
        return []

    def query_state(self, selector, **filters):
        assert selector == "messages"
        return self._messages


def _msg(role, tool_calls=None, tool_call_id=None):
    import json as _json
    return {
        "role": role,
        "tool_calls": _json.dumps(tool_calls) if tool_calls is not None else None,
        "tool_call_id": tool_call_id,
    }


def test_returns_none_for_non_chat_correlation():
    k = _StubKernel("c1", [], chat_events=False)
    assert _conversation_context_for_correlation(k, "sched_abc", "write_file") == (None, None)


def test_returns_none_when_no_chat_events_for_correlation():
    k = _StubKernel("c1", [], chat_events=False)
    assert _conversation_context_for_correlation(k, "chat_missing", "write_file") == (None, None)


def test_picks_unanswered_tool_call_when_multiple_same_name():
    msgs = [
        _msg("assistant", tool_calls=[{"id": "tc_old", "function": {"name": "write_file"}}]),
        _msg("tool", tool_call_id="tc_old"),  # answered
        _msg("assistant", tool_calls=[{"id": "tc_new", "function": {"name": "write_file"}}]),
    ]
    k = _StubKernel("conv-9", msgs, chat_events=True)
    conv_id, tc_id = _conversation_context_for_correlation(k, "chat_x", "write_file")
    assert conv_id == "conv-9"
    assert tc_id == "tc_new"


def test_returns_none_when_all_same_name_answered():
    msgs = [
        _msg("assistant", tool_calls=[{"id": "tc_a", "function": {"name": "write_file"}}]),
        _msg("tool", tool_call_id="tc_a"),
    ]
    k = _StubKernel("conv-1", msgs, chat_events=True)
    conv_id, tc_id = _conversation_context_for_correlation(k, "chat_y", "write_file")
    assert conv_id == "conv-1"
    assert tc_id is None


def test_ignores_different_action_names():
    msgs = [
        _msg("assistant", tool_calls=[{"id": "tc_other", "function": {"name": "read_file"}}]),
    ]
    k = _StubKernel("conv-2", msgs, chat_events=True)
    _, tc_id = _conversation_context_for_correlation(k, "chat_z", "write_file")
    assert tc_id is None


def test_no_action_returns_conv_only():
    k = _StubKernel("conv-3", [], chat_events=True)
    conv_id, tc_id = _conversation_context_for_correlation(k, "chat_w", None)
    assert conv_id == "conv-3"
    assert tc_id is None


def test_handles_alt_tool_call_shape_with_top_level_name():
    """Some legacy rows store name at top level instead of function.name."""
    msgs = [
        _msg("assistant", tool_calls=[{"id": "tc_alt", "name": "write_file"}]),
    ]
    k = _StubKernel("conv-4", msgs, chat_events=True)
    _, tc_id = _conversation_context_for_correlation(k, "chat_v", "write_file")
    assert tc_id == "tc_alt"
