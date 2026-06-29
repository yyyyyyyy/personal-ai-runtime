"""Lightweight activity audit log — append-only, for important operation auditing.

NOT used for event sourcing or state projection. All business state lives in SQLite tables.
"""

import json

from app.store.database import db


def log_activity(activity_type: str, payload: dict | None = None):
    """Record an important operation to the activity log."""
    payload_str = json.dumps(payload) if payload else None
    db.log_activity(activity_type, payload_str)
