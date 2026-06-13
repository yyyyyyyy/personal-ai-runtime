"""Tests for tool markup filtering and parsing."""

from app.core.agents.tool_markup import (
    has_tool_markup,
    parse_tool_calls,
    strip_tool_markup,
)

SAMPLE = (
    "好的\n"
    '<｜tool_calls> <｜invoke name="read_file">'
    '<｜parameter name="path" string="true">/tmp/Makefile</｜parameter>'
    '</｜invoke> <｜invoke name="shell_exec">'
    '<｜parameter name="command" string="true">ls</｜parameter>'
    "</｜invoke> </｜tool_calls>\n"
    "剩下的文字"
)


def test_has_tool_markup():
    assert has_tool_markup(SAMPLE)
    assert not has_tool_markup("plain text")


def test_strip_tool_markup():
    cleaned = strip_tool_markup("前缀" + SAMPLE + "后缀")
    assert "tool_calls" not in cleaned
    assert "invoke" not in cleaned
    assert "read_file" not in cleaned
    assert "好的" in cleaned
    assert "剩下的文字" in cleaned


def test_strip_empty():
    assert strip_tool_markup("") == ""
    assert strip_tool_markup(None) == ""


def test_parse_tool_calls():
    calls, cleaned = parse_tool_calls(SAMPLE)
    assert len(calls) == 2
    assert calls[0]["function_name"] == "read_file"
    assert '"path"' in calls[0]["arguments"]
    assert calls[1]["function_name"] == "shell_exec"
    assert '"command"' in calls[1]["arguments"]
    assert "tool_calls" not in cleaned


def test_parse_no_markup():
    calls, cleaned = parse_tool_calls("plain text")
    assert calls == []
    assert cleaned == "plain text"
