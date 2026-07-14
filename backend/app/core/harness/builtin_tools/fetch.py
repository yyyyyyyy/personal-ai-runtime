"""Fetch MCP Server — HTTP requests and web page content extraction."""

import json
import re

import httpx

from app.core.harness.url_safety import (
    UnsafeUrlError,
    create_ssrf_safe_async_client,
    validate_http_url,
)


class FetchServer:
    """HTTP request and web scraping with readability-like text extraction."""

    # Cap on raw bytes read from the network to prevent OOM from huge
    # responses. Set above the downstream text/html truncation limits (8000
    # chars of extracted text, 15000 chars of raw HTML) because HTML tag
    # stripping in _extract_text shrinks the payload significantly — a 50KB
    # HTML page commonly yields <8KB of readable text.
    MAX_RESPONSE_BYTES = 50_000

    async def fetch_url(self, url: str, extract_text: bool = True) -> str:
        """Fetch a URL and optionally extract readable text content.

        Args:
            url: The URL to fetch
            extract_text: If True, extract main text content. If False, return raw HTML.
        """
        try:
            safe_url = validate_http_url(url)

            async with create_ssrf_safe_async_client(
                timeout=20.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; PersonalAI-Runtime/0.1; +https://personal-ai.runtime)"
                },
            ) as client:
                # Stream the response so we can bail out early if the server
                # tries to send an excessively large body.
                html = ""
                final_url = safe_url
                status = 0
                async with client.stream("GET", safe_url) as resp:
                    resp.raise_for_status()
                    final_url = str(resp.url)
                    status = resp.status_code
                    chunks: list[bytes] = []
                    total = 0
                    truncated = False
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > self.MAX_RESPONSE_BYTES:
                            truncated = True
                            break
                        chunks.append(chunk)
                    if truncated:
                        # Stop reading / drop the connection so a huge body
                        # does not keep draining into the process.
                        await resp.aclose()
                    html = b"".join(chunks).decode("utf-8", errors="replace")

                if extract_text:
                    text = self._extract_text(html)
                    if len(text) > 8000:
                        text = text[:8000] + "\n... [content truncated]"
                    return json.dumps({
                        "url": final_url,
                        "status": status,
                        "title": self._extract_title(html),
                        "content": text[:8000],
                    }, ensure_ascii=False)
                else:
                    if len(html) > 15000:
                        html = html[:15000] + "\n... [content truncated]"
                    return json.dumps({
                        "url": final_url,
                        "status": status,
                        "content": html,
                    }, ensure_ascii=False)

        except UnsafeUrlError as e:
            return json.dumps({"error": f"Blocked URL: {e}"})
        except httpx.HTTPStatusError as e:
            return json.dumps({"error": f"HTTP {e.response.status_code}: {e.response.reason_phrase}"})
        except httpx.TimeoutException:
            return json.dumps({"error": "Request timed out after 20 seconds"})
        except Exception as e:
            return json.dumps({"error": f"Fetch failed: {str(e)}"})

    def _extract_title(self, html: str) -> str:
        """Extract page title from HTML."""
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()[:200]
        return ""

    def _extract_text(self, html: str) -> str:
        """Extract readable text from HTML using basic heuristics.

        Removes scripts, styles, and extracts text from body content.
        """
        # Remove script and style elements
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<noscript[^>]*>.*?</noscript>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML comments
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

        # Replace common block elements with newlines
        for tag in ["p", "div", "article", "section", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr"]:
            html = re.sub(f"<{tag}[^>]*>", "\n", html, flags=re.IGNORECASE)
            html = re.sub(f"</{tag}>", "\n", html, flags=re.IGNORECASE)

        # Remove remaining HTML tags
        html = re.sub(r"<[^>]+>", " ", html)

        # Decode common HTML entities
        html = html.replace("&amp;", "&")
        html = html.replace("&lt;", "<")
        html = html.replace("&gt;", ">")
        html = html.replace("&quot;", '"')
        html = html.replace("&#39;", "'")
        html = html.replace("&nbsp;", " ")
        html = re.sub(r"&#\d+;", " ", html)

        # Collapse whitespace
        lines = [line.strip() for line in html.splitlines()]
        lines = [line for line in lines if line]
        text = "\n".join(lines)

        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()


fetch_server = FetchServer()
