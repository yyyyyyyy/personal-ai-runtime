"""Shell MCP Server — whitelist-based subprocess execution."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

from app.config import BASE_DIR, settings
from app.core.harness.url_safety import UnsafeUrlError, validate_http_url


class ShellServer:
    """Safe shell command execution with whitelist enforcement.

    Two tiers of commands keep the default attack surface small while letting
    operators opt into riskier tools:

    * ``ALLOWED_COMMANDS`` — read-only / development commands enabled by
      default (ls, cat, git, python, npm, …).
    * ``_EXTENDED_COMMANDS`` — high-risk commands (rm, chmod, ssh, gpg,
      package managers, process killers, mount, …) that require explicit
      opt-in via ``settings.shell_extra_commands``.
    """

    ALLOWED_COMMANDS = [
        # System info
        "echo", "date", "whoami", "hostname", "uname",
        # Shell basics (read-heavy; rm/chmod/chown are extended)
        "ls", "dir", "pwd", "cd", "cat", "head", "tail", "wc", "touch",
        "mkdir", "cp", "mv", "ln",
        # Process inspection (kill/killall/pkill are extended)
        "ps", "top", "pgrep", "lsof",
        # Disk & memory (read-only; mount/umount are extended)
        "df", "du", "free", "vm_stat",
        # Network inspection
        "ping", "traceroute", "ifconfig", "ipconfig", "ss", "netstat",
        "dig", "nslookup", "host", "whois",
        # Python
        "python", "python3", "pip", "pip3", "pytest", "uv", "uvx",
        # Node.js
        "node", "npm", "npx", "yarn", "pnpm",
        # Git
        "git",
        # Compression
        "tar", "gzip", "gunzip", "zip", "unzip",
        # Text processing
        "grep", "egrep", "rg", "awk", "sed", "sort", "uniq", "cut",
        "tr", "diff", "find", "xargs", "tee",
        # Formatting
        "jq", "yq",
        # System state
        "env", "export", "source", "which", "type",
    ]

    # High-risk commands — only enabled when listed in SHELL_EXTRA_COMMANDS.
    _EXTENDED_COMMANDS = frozenset({
        # Destructive file ops
        "rm", "chmod", "chown",
        # Process management
        "kill", "killall", "pkill",
        # Filesystem mount
        "mount", "umount",
        # System package managers (can install anything)
        "brew", "apt", "apt-get", "dpkg", "rpm", "snap",
        # Crypto / remote access (key material, remote shells)
        "gpg", "ssh", "ssh-keygen", "ssh-add",
    })

    # Shell metacharacters — never pass to a shell.
    # && is handled separately by _split_and_execute; all other metacharacters
    # (|, ||, ;, `, $, <, >, (, )) are still rejected.
    _METACHAR_RE = re.compile(r"[|;`$<>()]|\|\|")

    # Commands that escalate privileges — rejected at argv level (not substring
    # matching, which would false-positive on "pseudo", "subl", "summarize").
    _PRIVILEGE_ESCALATION_COMMANDS = frozenset({"sudo", "su", "doas"})

    def __init__(self) -> None:
        # Effective whitelist = safe default + opt-in extended commands.
        # Only commands that are actually in _EXTENDED_COMMANDS are honoured,
        # so the env var cannot smuggle in arbitrary names.
        enabled_extra = self._parse_extra_commands(settings.shell_extra_commands)
        self._effective_whitelist = set(self.ALLOWED_COMMANDS) | (
            self._EXTENDED_COMMANDS & enabled_extra
        )
        # Directories the shell tool may use as cwd. Default to the project
        # root so commands cannot roam the filesystem by setting cwd.
        self.allowed_cwd_dirs = self._parse_cwd_dirs(settings.shell_allowed_cwd)

    @staticmethod
    def _parse_extra_commands(raw: str) -> set[str]:
        if not raw.strip():
            return set()
        return {c.strip() for c in raw.split(",") if c.strip()}

    @staticmethod
    def _parse_cwd_dirs(raw: str) -> list[str]:
        if not raw.strip():
            return [str(Path(BASE_DIR).resolve())]
        dirs: list[str] = []
        for item in raw.split(","):
            item = item.strip()
            if item:
                dirs.append(str(Path(item).expanduser().resolve()))
        return dirs

    def _validate_cwd(self, cwd: str) -> str | None:
        """Return error message if ``cwd`` is outside the allowed directories."""
        if not cwd:
            return None  # caller will fall back to BASE_DIR
        try:
            target = Path(cwd).expanduser().resolve()
        except Exception:
            return f"Invalid cwd: {cwd}"
        for allowed in self.allowed_cwd_dirs:
            base = Path(allowed).resolve()
            if target == base or target.is_relative_to(base):
                return None
        return (
            f"Access denied: cwd '{cwd}' outside allowed directories. "
            f"Allowed: {', '.join(self.allowed_cwd_dirs)}"
        )

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

        try:
            argv = shlex.split(stripped, posix=not sys.platform.startswith("win"))
        except ValueError as exc:
            return f"Invalid command syntax: {exc}"

        if not argv:
            return "Empty command"

        return argv

    def _validate_argv(self, argv: list[str]) -> str | None:
        """Return error message if argv is not allowed.

        Dangerous-pattern checks run on the tokenized argv rather than the raw
        command string so that they cannot be evaded with extra whitespace,
        tabs, or argument reordering (e.g. ``rm  -rf`` / ``rm\t-rf``).
        """
        cmd_name = argv[0]

        # Privilege escalation — reject sudo/su/doas as the command itself.
        if cmd_name in self._PRIVILEGE_ESCALATION_COMMANDS:
            return f"Blocked pattern detected: '{cmd_name}'"

        # Destructive flag combinations — checked before the whitelist so they
        # are rejected even if the base command is whitelisted.
        destructive = self._destructive_pattern(cmd_name, argv[1:])
        if destructive:
            return f"Blocked pattern detected: '{destructive}'"

        if cmd_name not in self._effective_whitelist:
            return (
                f"Command '{cmd_name}' not in whitelist. "
                f"Allowed: {', '.join(sorted(self._effective_whitelist)[:10])}..."
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

    @staticmethod
    def _destructive_pattern(cmd_name: str, rest: list[str]) -> str | None:
        """Return a human-readable pattern name if argv is destructively unsafe.

        Token-level checks are robust against whitespace/Tab evasion and
        argument reordering (e.g. ``rm -rf /`` vs ``rm / -rf``).
        """
        if cmd_name == "rm" and any(tok in {"-rf", "-fr"} for tok in rest):
            return "rm -rf"
        if cmd_name == "chmod" and "777" in rest:
            return "chmod 777"
        # ``dd if=`` only matters when dd itself is invoked; it is not in the
        # whitelist, but we reject the pattern defensively in case it is added.
        if cmd_name == "dd" and any(tok.startswith("if=") for tok in rest):
            return "dd if="
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

        # Constrain cwd to the allowed directories; default to BASE_DIR when
        # unset so commands cannot run in an arbitrary location.
        cwd_err = self._validate_cwd(cwd)
        if cwd_err:
            return json.dumps({"error": cwd_err})
        effective_cwd = cwd or self.allowed_cwd_dirs[0]

        try:
            result = subprocess.run(
                parsed,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=effective_cwd,
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
        """List all allowed shell commands (safe default + opted-in extended)."""
        return json.dumps({"allowed_commands": sorted(self._effective_whitelist)})


shell_server = ShellServer()
