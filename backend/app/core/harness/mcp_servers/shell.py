"""Shell MCP Server — whitelist-based subprocess execution."""

import json
import subprocess


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

    def execute(self, command: str, cwd: str = "", timeout_seconds: int = 30) -> str:
        """Execute a whitelisted shell command."""
        cmd_name = command.strip().split()[0]

        # Check whitelist
        if cmd_name not in self.ALLOWED_COMMANDS:
            return json.dumps({
                "error": f"Command '{cmd_name}' not in whitelist. Allowed: {', '.join(self.ALLOWED_COMMANDS[:10])}...",
            })

        # Check blocked patterns
        for pattern in self.BLOCKED_PATTERNS:
            if pattern in command:
                return json.dumps({"error": f"Blocked pattern detected: '{pattern}'"})

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout_seconds, cwd=cwd or None,
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
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_allowed_commands(self) -> str:
        """List all allowed shell commands."""
        return json.dumps({"allowed_commands": self.ALLOWED_COMMANDS})


shell_server = ShellServer()
