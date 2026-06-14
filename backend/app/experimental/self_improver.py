"""Self Improver — collects feedback and improves prompts/behavior over time.

Status: EXPERIMENTAL — lives under `app/experimental/`, not wired into production.

All writes go through Kernel Event Log (FeedbackLogged events).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.core.runtime.kernel.constants import (
    AGGREGATE_FRICTION,
    EVENT_FEEDBACK_LOGGED,
)

if TYPE_CHECKING:
    from app.core.runtime.kernel import Kernel


class SelfImprover:
    """Manages feedback loops for continuous improvement."""

    def __init__(self, kernel: Kernel | None = None):
        from app.core.runtime.kernel_instance import kernel as default_kernel

        self._kernel = kernel or default_kernel

    def log_feedback(self, prompt_template: str, output: str, accepted: bool, reason: str = "") -> str:
        """Log a user decision for training data via Kernel Event Log."""
        feedback_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        self._kernel.emit_event(
            EVENT_FEEDBACK_LOGGED,
            AGGREGATE_FRICTION,
            feedback_id,
            payload={
                "prompt_template": prompt_template[:500],
                "output": output[:500],
                "accepted": accepted,
                "reason": reason,
                "logged_at": now,
            },
            actor="self_improver",
        )
        return feedback_id

    def get_accept_rate(self, prompt_version: str, days: int = 7) -> float:
        """Calculate acceptance rate for a prompt version from Event Log."""
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        events = self._kernel.read_events(type=EVENT_FEEDBACK_LOGGED, order="asc")
        matching = [
            e for e in events
            if prompt_version in json.dumps(e.payload or {})
            and (e.ts or "") >= cutoff
        ]
        if not matching:
            return 0.5
        accepted = sum(1 for e in matching if (e.payload or {}).get("accepted"))
        return accepted / len(matching)

    def compare_versions(self, version_a: str, version_b: str) -> dict:
        """Compare two prompt versions by acceptance rate."""
        return {
            "version_a": {"name": version_a, "rate": self.get_accept_rate(version_a)},
            "version_b": {"name": version_b, "rate": self.get_accept_rate(version_b)},
        }


self_improver = SelfImprover()
