"""Daily Review trigger — generates daily review and stores as notification."""

from datetime import datetime

from app.core.review_engine import review_engine
from app.product.notifications import create_notification, find_notification


async def generate_daily_review() -> dict | None:
    """Generate a daily review, notify the user, and return the review record."""
    today = datetime.now().strftime("%Y-%m-%d")
    title = f"每日复盘 - {today}"

    review_id = await review_engine.generate_daily_review(date=today)
    if not review_id:
        return None

    review = review_engine.get_review(review_id)
    if not review:
        return None

    if not find_notification("review", title):
        create_notification("review", title, review["content"][:1000], related_id=review_id)

    return review
