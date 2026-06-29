"""Typed payload and projection types for the Kernel ABI.

These TypedDict definitions replace bare dict[str, Any] in the Kernel API,
giving type-aware tooling and better documentation of the data contracts.
"""

from __future__ import annotations

from typing import TypedDict

# ── Event payloads ──────────────────────────────────────────────────────────


class GoalPayload(TypedDict, total=False):
    title: str
    description: str
    status: str
    progress: float
    importance: float
    urgency: float
    deadline: str | None
    parent_id: str | None


class TaskPayload(TypedDict, total=False):
    name: str
    description: str
    status: str
    priority: int
    parent_goal_id: str | None
    parent_task_id: str | None
    dependencies_json: str | None


class MemoryPayload(TypedDict, total=False):
    content: str
    category: str
    source: str
    confidence: float


class ApprovalPayload(TypedDict, total=False):
    action: str
    risk: str
    reason: str
    ctx: dict[str, object] | None


# ── Projection row types (query_state return values) ────────────────────────


class GoalProjection(TypedDict, total=False):
    id: str
    title: str
    description: str | None
    status: str
    progress: float
    importance: float
    urgency: float
    deadline: str | None
    parent_id: str | None
    created_at: str
    updated_at: str
    last_activity_at: str | None


class TaskProjection(TypedDict, total=False):
    id: str
    name: str
    description: str | None
    parent_goal_id: str | None
    parent_task_id: str | None
    status: str
    priority: int
    dependencies_json: str | None
    created_at: str
    updated_at: str


class MemoryProjection(TypedDict, total=False):
    id: str
    content: str
    category: str
    source: str | None
    embedding_id: str | None
    confidence: float
    derived_from_event: str | None
    decayed_at: str | None
    status: str
    origin: str
    claim_status: str | None
    created_at: str


class ApprovalProjection(TypedDict, total=False):
    id: str
    task_id: str | None
    action: str
    params: str | None
    proposed_by: str | None
    status: str
    created_at: str
    resolved_at: str | None
    resolved_by: str | None


class ActionProjection(TypedDict, total=False):
    id: str
    goal_id: str
    title: str
    status: str
    executable_plan: str | None
    created_at: str
    completed_at: str | None


class PatternProjection(TypedDict, total=False):
    id: str
    pattern_type: str
    metric: str
    window_days: int
    statistics: str
    evidence_chain: str
    created_at: str


# Union of all concrete projection types
ProjectionRow = (
    GoalProjection
    | TaskProjection
    | MemoryProjection
    | ApprovalProjection
    | ActionProjection
    | PatternProjection
)
