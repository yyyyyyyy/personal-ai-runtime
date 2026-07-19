"""Git MCP Server — repository status, diff, log, and safe operations."""

import json
import subprocess
from pathlib import Path

from app.core.harness.builtin_tools.filesystem import filesystem_server
from app.core.harness.subprocess_env import minimal_subprocess_env


class GitServer:
    """Git operations via subprocess with safety constraints.

    Repository paths must fall inside the same allowed directories as the
    filesystem tools — otherwise auto-allow ``git_status``/``git_log``/``git_diff``
    could probe arbitrary local repos.
    """

    def status(self, repo_path: str = ".") -> str:
        """Get the git status of a repository."""
        return self._run_git(repo_path, ["status", "--short", "--branch"])

    def log(self, repo_path: str = ".", max_count: int = 10) -> str:
        """Get recent git commit log."""
        return self._run_git(repo_path, ["log", f"--max-count={max_count}", "--oneline", "--decorate"])

    def diff(self, repo_path: str = ".", staged: bool = False) -> str:
        """Get current git diff."""
        args = ["diff"]
        if staged:
            args.append("--staged")
        return self._run_git(repo_path, args)

    def _run_git(self, repo_path: str, args: list[str]) -> str:
        repo = Path(repo_path).expanduser().resolve()
        if not filesystem_server.is_path_allowed(str(repo)):
            return json.dumps({
                "error": "Access denied: path outside allowed directories",
                "path": str(repo),
            })
        if not (repo / ".git").exists():
            return json.dumps({"error": f"Not a git repository: {repo_path}"})

        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=15,
                env=minimal_subprocess_env(),
            )
            return json.dumps({
                "command": f"git {' '.join(args)}",
                "repo": str(repo),
                "output": result.stdout or result.stderr,
                "exit_code": result.returncode,
            })
        except Exception as e:
            return json.dumps({"error": str(e)})


git_server = GitServer()
