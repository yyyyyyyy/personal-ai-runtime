"""Web Search MCP Server — search the web via DuckDuckGo or configurable engines."""

import json
from urllib.parse import quote

import httpx

# DuckDuckGo Instant Answer API (free, no API key needed)
DUCKDUCKGO_API = "https://api.duckduckgo.com/"


class WebSearchServer:
    """Web search via DuckDuckGo instant answers."""

    async def search(self, query: str, max_results: int = 5) -> str:
        """Search the web and return results."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Try DuckDuckGo Instant Answer API
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
                    return json.dumps({"error": f"Search failed with status {resp.status_code}"})

                data = resp.json()

                results = []

                # Abstract (instant answer)
                if data.get("AbstractText"):
                    results.append({
                        "title": data.get("AbstractSource", "DuckDuckGo"),
                        "url": data.get("AbstractURL", ""),
                        "snippet": data.get("AbstractText", ""),
                    })

                # Related topics
                related = data.get("RelatedTopics", [])
                for topic in related[:max_results]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append({
                            "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                            "url": topic.get("FirstURL", ""),
                            "snippet": topic.get("Text", ""),
                        })

                if not results:
                    # Fallback: generate a DuckDuckGo search URL
                    search_url = f"https://duckduckgo.com/?q={quote(query)}"
                    results.append({
                        "title": f"Search: {query}",
                        "url": search_url,
                        "snippet": f"No instant results available. Please visit {search_url} for full results.",
                    })

                if len(results) > max_results:
                    results = results[:max_results]

                return json.dumps({"query": query, "results": results}, indent=2, ensure_ascii=False)

        except httpx.TimeoutException:
            return json.dumps({"error": "Search request timed out"})
        except Exception as e:
            return json.dumps({"error": f"Search failed: {str(e)}"})


web_search_server = WebSearchServer()
