"""Streaming MeaningGate tests."""

from app.core.runtime.meaning_gate import gate_stream_delta


def test_stream_passes_through_mid_sentence():
    acc, delta, warnings = gate_stream_delta("你好", "，继续")
    assert acc == "你好，继续"
    assert delta == "，继续"
    assert warnings == []


def test_stream_softens_at_sentence_end():
    acc, delta, warnings = gate_stream_delta("", "你就是这样的人。")
    assert "系统推测" in acc or "倾向" in acc
    assert warnings
