"""Monthly Review trigger."""

import uuid
from datetime import datetime

from app.core.review_engine import review_engine
from app.store.database import db


def generate_monthly_review() -> dict | None:
    """Generate a monthly review and store as notification."""
    review_id = review_engine.generate_monthly_review()
    review = review_engine.get_review(review_id)

    if not review:
        return None

    notification_id = str(uuid.uuid4())
    title = f"每月复盘 - {review['period_start']} ~ {review['period_end']}"
    content = review["content"][:1000]

    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO notifications (id, type, title, content, created_at) VALUES (?, 'review', ?, ?, ?)",
            (notification_id, title, content, datetime.utcnow().isoformat()),
        )

    return {"id": notification_id, "type": "review", "title": title, "content": content}
