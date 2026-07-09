"""Dashboard API — exposes Personal Dashboard computed from Kernel ABI.

This endpoint is the "一致性测试床" — it proves a product feature can be
delivered using only Kernel ABI without bypassing Runtime boundaries.
Every data read goes through kernel.query_state / read_events / recall_memory.
"""

from fastapi import APIRouter

from app.product.personal_dashboard import generate_dashboard

router = APIRouter(tags=["dashboard"])


@router.get("")
async def get_dashboard():
    """Return a personal dashboard built entirely from Kernel ABI.

    Runtime consistency proof:
      - query_state for goals (work_items alias), timer_events, policy_events
      - read_events for recent system events
      - recall_memory for semantic belief recall
      - Zero SQL / storage / filesystem access outside Kernel
    """
    return generate_dashboard()
