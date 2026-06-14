"""Reviews API — query and trigger reviews."""

from fastapi import APIRouter, HTTPException

from app.core.review_engine import review_engine
from app.product.daily_review import generate_daily_review
from app.product.monthly_review import generate_monthly_review
from app.product.morning_brief import generate_morning_brief
from app.product.weekly_review import generate_weekly_review

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.get("/")
async def list_reviews(limit: int = 10):
    """List recent reviews."""
    return review_engine.list_reviews(limit=limit)


@router.get("/{review_id}")
async def get_review(review_id: str):
    """Get a specific review by ID."""
    review = review_engine.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@router.post("/trigger/daily")
async def trigger_daily():
    """Manually trigger a daily review."""
    result = await generate_daily_review()
    return {"status": "ok", "result": result}


@router.post("/trigger/weekly")
async def trigger_weekly():
    """Manually trigger a weekly review."""
    result = await generate_weekly_review()
    return {"status": "ok", "result": result}


@router.post("/trigger/monthly")
async def trigger_monthly():
    """Manually trigger a monthly review."""
    result = await generate_monthly_review()
    return {"status": "ok", "result": result}


@router.post("/trigger/morning-brief")
async def trigger_morning_brief():
    """Manually trigger a morning brief."""
    result = generate_morning_brief()
    return {"status": "ok", "result": result}
