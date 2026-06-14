"""Monthly Review trigger."""

from app.core.review_engine import review_engine
from app.product.notifications import create_notification, find_notification


async def generate_monthly_review() -> dict | None:
    """Generate a monthly review, notify the user, and return the review record."""
    review_id = await review_engine.generate_monthly_review()
    if not review_id:
        return None

    review = review_engine.get_review(review_id)
    if not review:
        return None

    title = f"每月复盘 - {review['period_start']} ~ {review['period_end']}"
    if not find_notification("review", title):
        create_notification("review", title, review["content"][:1000], related_id=review_id)

    return review
