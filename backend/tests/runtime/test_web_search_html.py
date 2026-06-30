"""Tests for DuckDuckGo HTML search parsing."""

import json

import pytest

from app.core.harness.builtin_tools.web_search import WebSearchServer

SAMPLE_HTML = """
<html><body>
<div class="result results_links results_links_deep web-result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage">Example Title</a>
  <a class="result__snippet">Example snippet text</a>
</div>
<div class="result results_links results_links_deep web-result">
  <a class="result__a" href="https://docs.python.org/3/">Python Docs</a>
  <a class="result__snippet">Official documentation</a>
</div>
</body></html>
"""


def test_parse_duckduckgo_html():
    server = WebSearchServer()
    results = server._parse_duckduckgo_html(SAMPLE_HTML, 5)
    assert len(results) == 2
    assert results[0]["title"] == "Example Title"
    assert results[0]["url"] == "https://example.com/page"
    assert "snippet" in results[0]


@pytest.mark.asyncio
async def test_search_uses_html_parser(monkeypatch):
    server = WebSearchServer()

    async def fake_html(query: str, max_results: int):
        return [{"title": "A", "url": "https://a.test", "snippet": "sa"}]

    monkeypatch.setattr(server, "_search_duckduckgo_html", fake_html)
    monkeypatch.setattr(server, "_search_duckduckgo_instant", lambda q, m: [])

    payload = json.loads(await server.search("test query", 3))
    assert payload["provider"] == "duckduckgo"
    assert payload["results"][0]["url"] == "https://a.test"
