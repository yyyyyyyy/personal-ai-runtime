"""Browser MCP Server — Playwright-based web automation (read-only by default)."""

import json


class BrowserServer:
    """Browser automation. Uses requests for read operations, Playwright stubs for automation."""

    def open_page(self, url: str) -> str:
        """Open a web page and return its content summary."""
        try:
            import asyncio

            import httpx

            async def fetch():
                async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                    resp = await client.get(url, headers={"User-Agent": "PersonalAIOS/1.0"})
                    return resp.text[:5000], resp.status_code

            text, status = asyncio.run(fetch())
            title = ""
            for line in text.splitlines():
                if "<title>" in line:
                    title = line.split("<title>")[1].split("</title>")[0].strip()
                    break

            return json.dumps({
                "url": url,
                "status": status,
                "title": title,
                "content_preview": text[:1000],
            })
        except Exception as e:
            return json.dumps({"error": str(e), "url": url})

    def search_and_extract(self, query: str, site: str = "") -> str:
        """Search a site and extract text content."""
        search_url = f"https://duckduckgo.com/html/?q={query}"
        if site:
            search_url += f"+site%3A{site}"
        return self.open_page(search_url)

    def take_screenshot(self, url: str) -> str:
        """Take a screenshot of a webpage (requires Playwright)."""
        return json.dumps({"error": "Screenshots require Playwright installation: pip install playwright"})


browser_server = BrowserServer()
