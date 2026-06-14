"""Weekly Review trigger."""

from app.core.review_engine import review_engine
from app.product.notifications import create_notification, find_notification


async def generate_weekly_review() -> dict | None:
    """Generate a weekly review and store as notification."""
    review_id = await review_engine.generate_weekly_review()
    review = review_engine.get_review(review_id)

    if not review:
        return None

    title = f"每周复盘 - {review['period_start']} ~ {review['period_end']}"
    existing = find_notification("review", title)
    if existing:
        return existing

    return create_notification("review", title, review["content"][:1000])
