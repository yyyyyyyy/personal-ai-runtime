"""Critic Agent — audits executor outputs, rejects unauthorized operations.

Lightweight safety gate using local model + rule-based checks.
"""

FORBIDDEN_PATTERNS = ["rm -rf", "DROP TABLE", "DELETE FROM", "shutdown", "format"]


class CriticAgent:
    """Audits step outputs and enforces safety rules."""

    def __init__(self, rejection_threshold: float = 0.3):
        self.rejection_threshold = rejection_threshold
        self.total_checks = 0
        self.total_rejections = 0

    def audit_step(self, tool_name: str, params: dict, result: str | None = None) -> bool:
        """Audit a single execution step. Returns True if safe, False if rejected."""
        self.total_checks += 1

        # Rule 1: Check for forbidden patterns in params
        params_str = str(params).lower()
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.lower() in params_str:
                self.total_rejections += 1
                return False

        # Rule 2: Write operations need explicit user approval
        dangerous_tools = {"write_file", "shell_exec", "git_push", "send_email"}
        if tool_name in dangerous_tools:
            is_approved = params.get("_approved", False)
            if not is_approved:
                self.total_rejections += 1
                return False

        return True

    def rejection_rate(self) -> float:
        if self.total_checks == 0:
            return 0.0
        return self.total_rejections / self.total_checks

    def should_replan(self) -> bool:
        """Check if Planner needs to re-generate plan due to high rejection rate."""
        return self.rejection_rate() > self.rejection_threshold


critic = CriticAgent()
