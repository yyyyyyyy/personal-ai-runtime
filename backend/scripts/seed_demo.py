#!/usr/bin/env python3
"""Seed the local database with demo goals, memories, and a sample conversation.

Safe to run multiple times — skips if demo markers already exist.
Requires LLM_API_KEY in environment (use any non-empty value for seeding only).
"""

from __future__ import annotations

import os
import sys
import uuid

os.environ.setdefault("LLM_API_KEY", "demo-seed-only")

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

DEMO_GOAL_TITLE = "【Demo】完成用户验证访谈"
DEMO_CONV_TITLE = "【Demo】规划本周工作"
DEMO_MEMORY_SNIPPET = "偏好本地优先、可随时导出的个人 AI 助手"


def _demo_exists() -> bool:
    from app.core.runtime.kernel_instance import kernel

    goals = kernel.query_state("goals", limit=200)
    return any(g.get("title") == DEMO_GOAL_TITLE for g in goals)


def seed() -> dict:
    from app.core.agents.conversation import ConversationAPI, ConversationManager
    from app.core.agents.memory_engine import memory_engine
    from app.core.runtime.kernel_instance import kernel

    if _demo_exists():
        print("Demo data already present — skipping.")
        return {"status": "skipped"}

    goal_id = str(uuid.uuid4())
    kernel.emit_event(
        type="GoalCreated",
        aggregate_type="goal",
        aggregate_id=goal_id,
        payload={
            "title": DEMO_GOAL_TITLE,
            "description": "邀请 5 位朋友试用两周，记录 D7 留存与导出使用率。",
            "importance": 0.9,
            "urgency": 0.7,
            "deadline": None,
            "parent_id": None,
        },
        actor="user",
    ).aggregate_id

    kernel.emit_event(
        type="GoalCreated",
        aggregate_type="goal",
        aggregate_id=str(uuid.uuid4()),
        payload={
            "title": "【Demo】整理 README 截图与上手文档",
            "description": "让新用户 5 分钟内看懂产品差异。",
            "importance": 0.6,
            "urgency": 0.5,
            "deadline": None,
            "parent_id": None,
        },
        actor="user",
    )

    memory_engine.store_memory(
        DEMO_MEMORY_SNIPPET,
        category="preference",
        source="demo_seed",
        actor="user",
        confidence=0.85,
    )
    memory_engine.store_memory(
        "正在构建 Personal AI Runtime 的 Event Log 导出能力作为数据主权护城河。",
        category="fact",
        source="demo_seed",
        actor="extractor",
        confidence=0.75,
    )

    conv = ConversationAPI.create(title=DEMO_CONV_TITLE)
    conv_id = conv["id"]
    mgr = ConversationManager(conversation_id=conv_id)
    mgr.save_user_message("帮我列一下本周最重要的三件事，并记住我偏好本地部署。")
    mgr.save_assistant_message(
        "好的。根据你的目标，本周建议优先：\n"
        "1. 招募 5 位内测用户\n"
        "2. 跑通 make dev + 导出备份\n"
        "3. 收集第一轮反馈\n\n"
        "我已记下你偏好本地优先、可导出的助手。"
    )

    print("Demo data seeded:")
    print(f"  - goals: 2 (including {goal_id[:8]}…)")
    print("  - memories: 2")
    print(f"  - conversation: {conv_id} ({DEMO_CONV_TITLE})")
    print("Open http://localhost:5173 — check Goals / Memories / Chat.")
    return {"status": "ok", "conversation_id": conv_id, "goal_id": goal_id}


if __name__ == "__main__":
    seed()
