"""Git MCP Server — repository status, diff, log, and safe operations."""

import json
import subprocess
from pathlib import Path


class GitServer:
    """Git operations via subprocess with safety constraints."""

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

    def branch(self, repo_path: str = ".") -> str:
        """List branches."""
        return self._run_git(repo_path, ["branch", "-a"])

    def stash_list(self, repo_path: str = ".") -> str:
        """List stashes."""
        return self._run_git(repo_path, ["stash", "list"])

    def _run_git(self, repo_path: str, args: list[str]) -> str:
        repo = Path(repo_path).expanduser().resolve()
        if not (repo / ".git").exists():
            return json.dumps({"error": f"Not a git repository: {repo_path}"})

        try:
            result = subprocess.run(
                ["git"] + args, cwd=str(repo),
                capture_output=True, text=True, timeout=15,
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
