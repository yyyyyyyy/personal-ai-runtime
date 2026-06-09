"""Self Improver — collects feedback and improves prompts/behavior over time.

Tracks user approvals/rejections, manages prompt templates with versioning.
"""

import json
import uuid
from datetime import datetime

from app.store.database import db


class SelfImprover:
    """Manages feedback loops for continuous improvement."""

    def log_feedback(self, prompt_template: str, output: str, accepted: bool, reason: str = ""):
        """Log a user decision for training data."""
        feedback_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        with db.get_db() as conn:
            conn.execute(
                """INSERT INTO activity_log (type, payload, timestamp)
                   VALUES (?, ?, ?)""",
                (
                    "feedback",
                    json.dumps({
                        "prompt_template": prompt_template[:500],
                        "output": output[:500],
                        "accepted": accepted,
                        "reason": reason,
                    }),
                    now,
                ),
            )
        return feedback_id

    def get_accept_rate(self, prompt_version: str, days: int = 7) -> float:
        """Calculate acceptance rate for a prompt version."""
        with db.get_db() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as c FROM activity_log WHERE type = 'feedback' AND payload LIKE ?",
                (f"%{prompt_version}%",),
            ).fetchone()["c"]
            accepted = conn.execute(
                "SELECT COUNT(*) as c FROM activity_log WHERE type = 'feedback' AND payload LIKE ? AND payload LIKE '%\"accepted\": true%'",
                (f"%{prompt_version}%",),
            ).fetchone()["c"]

        return accepted / total if total > 0 else 0.5

    def compare_versions(self, version_a: str, version_b: str) -> dict:
        """Compare two prompt versions by acceptance rate."""
        return {
            "version_a": {"name": version_a, "rate": self.get_accept_rate(version_a)},
            "version_b": {"name": version_b, "rate": self.get_accept_rate(version_b)},
        }


self_improver = SelfImprover()
