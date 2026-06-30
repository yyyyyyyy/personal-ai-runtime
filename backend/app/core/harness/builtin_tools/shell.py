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
        # System info
        "echo", "date", "whoami", "hostname", "uname",
        # Shell basics
        "ls", "dir", "pwd", "cd", "cat", "head", "tail", "wc", "touch",
        "mkdir", "cp", "mv", "rm", "chmod", "chown", "ln",
        # Process management
        "ps", "top", "kill", "killall", "pgrep", "pkill", "lsof",
        # Disk & memory
        "df", "du", "free", "vm_stat", "mount", "umount",
        # Network
        "ping", "traceroute", "ifconfig", "ipconfig", "ss", "netstat",
        "dig", "nslookup", "host", "whois",
        # Python
        "python", "python3", "pip", "pip3", "pytest", "uv", "uvx",
        # Node.js
        "node", "npm", "npx", "yarn", "pnpm",
        # Git
        "git",
        # System package managers
        "brew", "apt", "apt-get", "dpkg", "rpm", "snap",
        # Compression
        "tar", "gzip", "gunzip", "zip", "unzip",
        # Text processing
        "grep", "egrep", "rg", "awk", "sed", "sort", "uniq", "cut",
        "tr", "diff", "find", "xargs", "tee",
        # Docker (read-only operations)
        "docker",
        # Formatting
        "jq", "yq",
        # System state
        "env", "export", "source", "which", "type",
        # GPG / SSH
        "gpg", "ssh", "ssh-keygen", "ssh-add",
    ]

    BLOCKED_PATTERNS = [
        "rm -rf", "sudo", "su ", "chmod 777", "fork bomb",
        "> /dev/", "dd if=", ":(){ :|:& };:",
    ]

    # Shell metacharacters — never pass to a shell.
    # && is handled separately by _split_and_execute; all other metacharacters
    # (|, ||, ;, `, $, <, >, (, )) are still rejected.
    _METACHAR_RE = re.compile(r"[|;`$<>()]|\|\|")

    def _split_chained_commands(self, command: str) -> list[str]:
        """Split a chained command (cmd1 && cmd2) into individual commands."""
        parts = command.split("&&")
        return [p.strip() for p in parts if p.strip()]

    # Dangerous flags for interpreters that can execute arbitrary code.
    DANGEROUS_FLAGS: dict[str, frozenset[str]] = {
        "python": frozenset({"-c", "-m"}),
        "python3": frozenset({"-c", "-m"}),
        "pytest": frozenset({"-c", "-m"}),
        "node": frozenset({"-e", "--eval", "-p", "--print"}),
        "npm": frozenset({"-e", "--eval"}),
        "npx": frozenset({"-c", "--node-arg", "-e", "--eval"}),
        "yarn": frozenset({"-e", "--eval"}),
        "pnpm": frozenset({"-e", "--eval"}),
        "pip": frozenset({"-c"}),
        "pip3": frozenset({"-c"}),
        "brew": frozenset({"-c"}),
        "docker": frozenset({"--config"}),
        "ssh": frozenset({"-o", "ProxyCommand"}),
        "awk": frozenset({"-e", "--exec"}),
        "sed": frozenset({"-e", "--expression"}),
    }

    def _parse_argv(self, command: str) -> list[str] | str:
        """Parse command into argv. Returns error message string on failure."""
        stripped = command.strip()
        if not stripped:
            return "Empty command"

        if self._METACHAR_RE.search(stripped):
            return (
                "Shell metacharacters and command chaining are not allowed. "
                "Use '&&' to chain commands instead, or run ONE command."
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
        """Execute whitelisted commands without invoking a shell.

        If the command contains &&, it is automatically split into individual
        commands that are run sequentially. Each command gets the full timeout.
        The first failure stops the chain.
        """
        parts = self._split_chained_commands(command)
        if len(parts) > 1:
            results = []
            for i, part in enumerate(parts):
                r = self._run_single(part, cwd, timeout_seconds)
                results.append(r)
                # Check if this command returned an error — if so, stop the chain
                try:
                    data = json.loads(r)
                    if data.get("error"):
                        return json.dumps({
                            "chained": True,
                            "commands": parts,
                            "completed": i + 1,
                            "stopped_at_command": i + 1,
                            "results": results,
                            "note": f"Stopped at command {i+1}/{len(parts)} due to error.",
                        })
                except json.JSONDecodeError:
                    pass
            return json.dumps({
                "chained": True,
                "commands": parts,
                "results": [json.loads(r) for r in results],
            })

        return self._run_single(command, cwd, timeout_seconds)

    def _run_single(self, command: str, cwd: str = "", timeout_seconds: int = 30) -> str:
        """Execute a single command (no chaining)."""
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
