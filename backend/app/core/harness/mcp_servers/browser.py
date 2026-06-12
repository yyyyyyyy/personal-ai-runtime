"""Browser MCP Server — Playwright-based web automation (read-only by default)."""

import json

import httpx

from app.core.harness.url_safety import UnsafeUrlError, validate_http_url


class BrowserServer:
    """Browser automation. Uses httpx for read operations, Playwright stubs for automation."""

    async def open_page(self, url: str) -> str:
        """Open a web page and return its content summary."""
        try:
            safe_url = validate_http_url(url)

            async def _redirect_hook(response: httpx.Response) -> None:
                if response.is_redirect and response.next_request is not None:
                    validate_http_url(str(response.next_request.url))

            async with httpx.AsyncClient(
                timeout=20,
                follow_redirects=True,
                event_hooks={"response": [_redirect_hook]},
                headers={"User-Agent": "PersonalAIRuntime/1.0"},
            ) as client:
                resp = await client.get(safe_url)
                text = resp.text[:5000]
                status = resp.status_code

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
        except UnsafeUrlError as e:
            return json.dumps({"error": f"Blocked URL: {e}", "url": url})
        except Exception as e:
            return json.dumps({"error": str(e), "url": url})

    async def search_and_extract(self, query: str, site: str = "") -> str:
        """Search a site and extract text content."""
        search_url = f"https://duckduckgo.com/html/?q={query}"
        if site:
            search_url += f"+site%3A{site}"
        return await self.open_page(search_url)

    def take_screenshot(self, url: str) -> str:
        """Take a screenshot of a webpage (requires Playwright)."""
        return json.dumps({"error": "Screenshots require Playwright installation: pip install playwright"})


browser_server = BrowserServer()
