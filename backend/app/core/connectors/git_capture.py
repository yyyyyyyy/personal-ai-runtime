"""Git Capture Connector — collects Git commit activity as Experience events.

Scans configured local Git repositories and emits GitCommitCaptured events
for commits within the date range. Only stores metadata (repo, message summary,
file count, timestamp), never code content.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_REPO_PATHS: list[str] = []


def _kernel():
    from app.core.runtime import kernel_instance
    return kernel_instance.kernel


def _get_repo_paths() -> list[Path]:
    """Get configured Git repository paths (from env or sensible defaults)."""
    repos_env = getattr(settings, "git_repo_paths", None)
    if repos_env:
        return [Path(p.strip()) for p in str(repos_env).split(",") if p.strip()]
    # Default: scan common dev directories
    candidates = [
        Path.home() / "projects",
        Path.home() / "dev",
        Path.home() / "code",
    ]
    return [p for p in candidates if p.is_dir()]


def _parse_git_log(repo: Path, since: str, until: str) -> list[dict]:
    """Run git log in repo and return parsed commit entries."""
    try:
        result = subprocess.run(
            [
                "git", "-C", str(repo),
                "log",
                f"--since={since}",
                f"--until={until}",
                "--format=%H|%ai|%s|%an",
                "--shortstat",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("git log failed for %s", repo)
        return []

    if result.returncode != 0:
        return []

    commits: list[dict] = []
    current: dict | None = None
    for line in result.stdout.strip().split("\n"):
        if "|" in line and not line.strip().startswith(" "):
            parts = line.split("|", 3)
            if len(parts) >= 4:
                current = {
                    "hash": parts[0].strip()[:8],
                    "date": parts[1].strip(),
                    "message": parts[2].strip()[:200],
                    "author": parts[3].strip(),
                }
        elif current and "files changed" in line:
            parts = line.strip().split(",")
            stats = {}
            for p in parts:
                p = p.strip()
                if "file" in p:
                    stats["files"] = int(p.split()[0])
                elif "insertion" in p:
                    stats["insertions"] = int(p.split()[0])
                elif "deletion" in p:
                    stats["deletions"] = int(p.split()[0])
            current["stats"] = stats
            commits.append(current)
            current = None
    return commits


def capture_git_activity(*, lookback_days: int = 1) -> int:
    """Capture Git commits from the last N days. Returns event count."""
    repos = _get_repo_paths()
    if not repos:
        return 0

    until = datetime.now(UTC).isoformat()
    since = (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat()
    count = 0
    k = _kernel()

    for repo in repos:
        if not (repo / ".git").is_dir():
            continue
        commits = _parse_git_log(repo, since, until)
        repo_name = repo.name
        for commit in commits:
            k.emit_event(
                "GitCommitCaptured",
                "experience",
                f"git_{commit['hash']}",
                payload={
                    "repo": repo_name,
                    "message": commit.get("message", ""),
                    "files_changed": commit.get("stats", {}).get("files", 0),
                    "timestamp": commit.get("date", ""),
                },
                actor="world",
            )
            count += 1

    if count:
        logger.info("GitCapture: %d commits from %d repos", count, len(repos))
    return count
