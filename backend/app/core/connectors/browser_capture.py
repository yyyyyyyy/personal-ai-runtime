"""Browser History Capture Connector — collects browsing activity as Experience events.

Reads Chrome/Chromium History SQLite database (read-only), extracts visited URLs
with title and visit count. Privacy-preserving: only stores domain and title
summary, never query strings or full URLs.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# Chrome/Chromium History DB paths (platform-specific)
_CHROME_HISTORY_PATHS = {
    "win32": [
        Path.home() / "AppData/Local/Google/Chrome/User Data/Default/History",
        Path.home() / "AppData/Local/Chromium/User Data/Default/History",
        Path.home() / "AppData/Local/Microsoft/Edge/User Data/Default/History",
    ],
    "darwin": [
        Path.home() / "Library/Application Support/Google/Chrome/Default/History",
    ],
    "linux": [
        Path.home() / ".config/google-chrome/Default/History",
        Path.home() / ".config/chromium/Default/History",
    ],
}


def _kernel():
    from app.core.runtime import kernel_instance
    return kernel_instance.kernel


def _find_history_db() -> Path | None:
    """Find the first available browser history database."""
    import sys
    paths = _CHROME_HISTORY_PATHS.get(sys.platform, [])
    for p in paths:
        if p.is_file():
            return p
    return None


def _extract_domain(url: str) -> str:
    """Extract domain from URL, stripping protocol and path."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path.split("/")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain[:100]


def capture_browser_activity(*, lookback_days: int = 1) -> int:
    """Capture browsing activity from the last N days. Returns event count."""
    history_path = _find_history_db()
    if not history_path:
        return 0

    cutoff = int((datetime.now(UTC) - timedelta(days=lookback_days)).timestamp() * 1_000_000)

    try:
        conn = sqlite3.connect(f"file:{history_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """SELECT url, title, visit_count, last_visit_time
               FROM urls
               WHERE last_visit_time > ?
               ORDER BY last_visit_time DESC
               LIMIT 500""",
            (cutoff,),
        ).fetchall()
        conn.close()
    except Exception as exc:
        logger.warning("Browser capture failed: %s", exc)
        return 0

    count = 0
    k = _kernel()
    seen: set[str] = set()

    for row in rows:
        domain = _extract_domain(row["url"])
        if domain in seen:
            continue
        seen.add(domain)

        title = (row["title"] or "")[:200]
        k.emit_event(
            "BrowserActivityCaptured",
            "experience",
            f"browse_{domain.replace('.', '_')[:40]}",
            payload={
                "domain": domain,
                "title": title,
                "visit_count": row["visit_count"] or 0,
            },
            actor="world",
        )
        count += 1

    if count:
        logger.info("BrowserCapture: %d unique domains", count)
    return count
