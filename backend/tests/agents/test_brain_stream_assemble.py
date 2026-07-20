"""Unit tests for brain_stream_assemble."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.agents.brain_stream_assemble import AssembledStream, iter_assembled_stream


def _chunk(*, content: str | None = None, tool_calls=None, usage=None, choices=None):
    if choices is not None:
        return SimpleNamespace(choices=choices, usage=usage)
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta)
    return SimpleNamespace(choices=[choice], usage=usage)


def _tool_delta(*, index: int, id: str = "", name: str = "", arguments: str = ""):
    fn = SimpleNamespace(name=name or None, arguments=arguments or None)
    return SimpleNamespace(index=index, id=id or None, function=fn)


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        async def _gen():
            for c in self._chunks:
                yield c

        return _gen()


async def _assemble(chunks) -> AssembledStream:
    result: AssembledStream | None = None
    async for evt in iter_assembled_stream(_FakeStream(chunks)):
        if evt["type"] == "_stream_assembled":
            result = evt["result"]
    assert result is not None
    return result


@pytest.mark.asyncio
async def test_iter_assembled_stream_text_deltas_and_result():
    stream = _FakeStream([
        _chunk(content="Hello "),
        _chunk(content="world"),
    ])
    deltas: list[str] = []
    result: AssembledStream | None = None
    async for evt in iter_assembled_stream(stream):
        if evt["type"] == "text_delta":
            deltas.append(evt["content"])
        elif evt["type"] == "_stream_assembled":
            result = evt["result"]

    assert "".join(deltas) == "Hello world"
    assert result is not None
    assert result.visible_text == "Hello world"
    assert result.tool_calls == []


@pytest.mark.asyncio
async def test_iter_assembled_stream_tool_calls():
    result = await _assemble([
        _chunk(tool_calls=[_tool_delta(index=0, id="tc1", name="check_", arguments="")]),
        _chunk(tool_calls=[_tool_delta(index=0, name="inbox", arguments='{"a":')]),
        _chunk(tool_calls=[_tool_delta(index=0, arguments="1}")]),
    ])
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["function_name"] == "check_inbox"
    assert result.tool_calls[0]["arguments"] == '{"a":1}'


@pytest.mark.asyncio
async def test_iter_assembled_stream_recovers_markup_tool_calls():
    sample = (
        "<｜tool_calls>"
        "<｜invoke name=\"web_search\">"
        "<｜parameter name=\"query\">x</｜parameter>"
        "</｜invoke>"
        "</｜tool_calls>"
    )
    result = await _assemble([_chunk(content=sample)])
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["function_name"] == "web_search"
    assert "x" in result.tool_calls[0]["arguments"]
    assert "web_search" not in result.visible_text


@pytest.mark.asyncio
async def test_iter_assembled_stream_preserves_usage():
    usage = SimpleNamespace(prompt_tokens=11, completion_tokens=3)
    result = await _assemble([
        _chunk(content="hi"),
        _chunk(content="", usage=usage),
    ])
    assert result.usage is usage
    assert result.usage.prompt_tokens == 11


@pytest.mark.asyncio
async def test_iter_assembled_stream_skips_empty_choices():
    result = await _assemble([
        _chunk(choices=[]),
        _chunk(content="ok"),
    ])
    assert result.visible_text == "ok"
    assert result.tool_calls == []


@pytest.mark.asyncio
async def test_iter_assembled_stream_parallel_tool_indexes():
    result = await _assemble([
        _chunk(tool_calls=[
            _tool_delta(index=0, id="tc0", name="read_file", arguments='{"p":1}'),
            _tool_delta(index=1, id="tc1", name="web_search", arguments='{"q":"a"}'),
        ]),
    ])
    assert len(result.tool_calls) == 2
    names = {tc["function_name"] for tc in result.tool_calls}
    assert names == {"read_file", "web_search"}
    ids = {tc["id"] for tc in result.tool_calls}
    assert ids == {"tc0", "tc1"}


@pytest.mark.asyncio
async def test_iter_assembled_stream_plain_text_without_markup():
    result = await _assemble([_chunk(content="just text, no tools")])
    assert result.tool_calls == []
    assert result.visible_text == "just text, no tools"
    assert result.raw_text == "just text, no tools"
