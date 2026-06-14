"""Shell MCP Server — whitelist-based subprocess execution."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys

from app.core.harness.url_safety import UnsafeUrlError, validate_http_url


class ShellServer:
    """Safe shell command execution with whitelist enforcement."""

    ALLOWED_COMMANDS = [
        "echo", "date", "whoami", "hostname", "uname",
        "python", "python3", "pip", "pip3",
        "node", "npm", "npx",
        "git", "ls", "dir", "pwd", "cd",
        "cat", "head", "tail", "wc",
        "curl", "wget",
    ]

    BLOCKED_PATTERNS = [
        "rm -rf", "sudo", "su ", "chmod 777", "fork bomb",
        "> /dev/", "dd if=", ":(){ :|:& };:",
    ]

    # Shell metacharacters and command chaining — never pass to a shell.
    SHELL_METACHAR_RE = re.compile(r"[|&;`$<>()]|\|\||&&")

    # Dangerous flags for interpreters that can execute arbitrary code.
    DANGEROUS_FLAGS: dict[str, frozenset[str]] = {
        "python": frozenset({"-c", "-m"}),
        "python3": frozenset({"-c", "-m"}),
        "node": frozenset({"-e", "--eval"}),
        "pip": frozenset({"-c"}),
        "pip3": frozenset({"-c"}),
        "npx": frozenset({"-c", "--node-arg"}),
    }

    def _parse_argv(self, command: str) -> list[str] | str:
        """Parse command into argv. Returns error message string on failure."""
        stripped = command.strip()
        if not stripped:
            return "Empty command"

        if self.SHELL_METACHAR_RE.search(stripped):
            return (
                "Shell metacharacters and command chaining are not allowed. "
                "Run ONE command per call (e.g. 'pwd' not 'pwd && ls')."
            )

        for pattern in self.BLOCKED_PATTERNS:
            if pattern in stripped:
                return f"Blocked pattern detected: '{pattern}'"

        try:
            argv = shlex.split(stripped, posix=not sys.platform.startswith("win"))
        except ValueError as exc:
            return f"Invalid command syntax: {exc}"

        if not argv:
            return "Empty command"

        return argv

    def _validate_argv(self, argv: list[str]) -> str | None:
        """Return error message if argv is not allowed."""
        cmd_name = argv[0]
        if cmd_name not in self.ALLOWED_COMMANDS:
            return (
                f"Command '{cmd_name}' not in whitelist. "
                f"Allowed: {', '.join(self.ALLOWED_COMMANDS[:10])}..."
            )

        dangerous = self.DANGEROUS_FLAGS.get(cmd_name)
        if dangerous:
            for arg in argv[1:]:
                if arg in dangerous:
                    return f"Flag '{arg}' is not allowed for '{cmd_name}'"

        if cmd_name in {"curl", "wget"}:
            url_err = self._validate_http_urls_in_argv(argv)
            if url_err:
                return url_err

        return None

    def _validate_http_urls_in_argv(self, argv: list[str]) -> str | None:
        """Reject internal URLs passed to curl/wget."""
        for arg in argv[1:]:
            if arg.startswith("http://") or arg.startswith("https://"):
                try:
                    validate_http_url(arg)
                except UnsafeUrlError as exc:
                    return f"Blocked URL in command: {exc}"
        return None

    def execute(self, command: str, cwd: str = "", timeout_seconds: int = 30) -> str:
        """Execute a whitelisted command without invoking a shell."""
        parsed = self._parse_argv(command)
        if isinstance(parsed, str):
            return json.dumps({"error": parsed})

        err = self._validate_argv(parsed)
        if err:
            return json.dumps({"error": err})

        try:
            result = subprocess.run(
                parsed,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=cwd or None,
            )
            output = result.stdout or result.stderr
            return json.dumps({
                "command": command,
                "exit_code": result.returncode,
                "output": output[:5000],
                "output_length": len(output),
            })
        except subprocess.TimeoutExpired:
            return json.dumps({"error": f"Command timed out after {timeout_seconds}s"})
        except FileNotFoundError:
            return json.dumps({"error": f"Command not found: {parsed[0]}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_allowed_commands(self) -> str:
        """List all allowed shell commands."""
        return json.dumps({"allowed_commands": self.ALLOWED_COMMANDS})


shell_server = ShellServer()
