"""Web Search MCP Server — DuckDuckGo HTML + optional Instant Answer API."""

import json
import re
from html import unescape
from urllib.parse import quote, unquote

import httpx

from app.core.harness.url_safety import create_ssrf_safe_async_client

DUCKDUCKGO_API = "https://api.duckduckgo.com/"
DUCKDUCKGO_HTML = "https://html.duckduckgo.com/html/"


class WebSearchServer:
    """Web search with DuckDuckGo HTML results (primary) and Instant Answer fallback."""

    async def search(self, query: str, max_results: int = 5) -> str:
        max_results = max(1, min(max_results, 10))
        try:
            results = await self._search_duckduckgo_html(query, max_results)
            if not results:
                results = await self._search_duckduckgo_instant(query, max_results)
            if not results:
                search_url = f"https://duckduckgo.com/?q={quote(query)}"
                results = [{
                    "title": f"Search: {query}",
                    "url": search_url,
                    "snippet": f"No results parsed. Visit {search_url} manually.",
                }]
            return json.dumps({"query": query, "provider": "duckduckgo", "results": results}, indent=2, ensure_ascii=False)
        except httpx.TimeoutException:
            return json.dumps({"error": "Search request timed out"})
        except Exception as e:
            return json.dumps({"error": f"Search failed: {str(e)}"})

    async def _search_duckduckgo_html(self, query: str, max_results: int) -> list[dict]:
        async with create_ssrf_safe_async_client(
            timeout=20.0,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; PersonalAI-Runtime/1.0)",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        ) as client:
            resp = await client.post(
                DUCKDUCKGO_HTML,
                data={"q": query, "b": "", "kl": ""},
            )
            if resp.status_code not in (200, 202):
                return []
            return self._parse_duckduckgo_html(resp.text, max_results)

    def _parse_duckduckgo_html(self, html: str, max_results: int) -> list[dict]:
        results: list[dict] = []
        blocks = re.split(r'<div class="result\s+results_links[^"]*"[^>]*>', html)
        for block in blocks[1:]:
            title_match = re.search(
                r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                block,
                re.DOTALL | re.IGNORECASE,
            )
            if not title_match:
                continue
            url = self._normalize_ddg_url(title_match.group(1))
            title = self._strip_tags(title_match.group(2))
            snippet_match = re.search(
                r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)>',
                block,
                re.DOTALL | re.IGNORECASE,
            )
            snippet = self._strip_tags(snippet_match.group(1)) if snippet_match else ""
            if url and title:
                results.append({"title": title, "url": url, "snippet": snippet})
            if len(results) >= max_results:
                break
        return results

    def _normalize_ddg_url(self, href: str) -> str:
        href = unescape(href.strip())
        if href.startswith("//"):
            href = "https:" + href
        if "uddg=" in href:
            match = re.search(r"uddg=([^&]+)", href)
            if match:
                return unquote(match.group(1))
        return href

    def _strip_tags(self, text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text)
        return unescape(text).strip()

    async def _search_duckduckgo_instant(self, query: str, max_results: int) -> list[dict]:
        async with create_ssrf_safe_async_client(timeout=15.0) as client:
            resp = await client.get(
                DUCKDUCKGO_API,
                params={
                    "q": query,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1",
                },
            )
            if resp.status_code not in (200, 202):
                return []
            data = resp.json()

        results: list[dict] = []
        if data.get("AbstractText"):
            results.append({
                "title": data.get("AbstractSource", "DuckDuckGo"),
                "url": data.get("AbstractURL", ""),
                "snippet": data.get("AbstractText", ""),
            })
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                    "url": topic.get("FirstURL", ""),
                    "snippet": topic.get("Text", ""),
                })
        return results[:max_results]


web_search_server = WebSearchServer()
