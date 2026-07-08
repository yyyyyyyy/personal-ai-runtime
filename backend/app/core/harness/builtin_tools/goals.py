"""Goals MCP Server — let AI manage user goals within conversations.

Bridges the gap between conversation and goal management: AI can create goals,
update progress, and mark goals complete without the user switching to the
Goals page.

Architectural split (closes ARCHITECTURE_SURVIVAL_REVIEW Critical #2):

- ``GoalsServer`` is the LLM-facing surface. Its methods are async and go
  through ``kernel.invoke_capability``, so every goal write traverses the
  3-gate authorization (forbidden → principal grant → pre-approved/risk).
- ``_writer_*`` module-level functions are the real tool handlers registered
  with ``mcp_hub``. They perform the actual ``emit_event`` and run only after
  the gate has allowed the call, so ``CapabilityInvoked`` is always emitted
  alongside the ``WorkItem*`` event.

Splitting these two roles avoids the previous architecture where
``GoalsServer`` itself emitted ``WorkItem*`` events, bypassing the gate
entirely and rendering ``requires_confirmation=True`` a no-op.
"""
import json
import uuid

# ─── Capability handlers (called by mcp_hub after gate allows) ──────────────
# These own the emit_event side effects. Registered as tool handlers below.


def _writer_create_goal(
    title: str,
    description: str = "",
    importance: float = 0.5,
    deadline: str = "",
) -> str:
    """Tool handler — emit WorkItemCreated for a new goal.

    Invoked only after ``invoke_capability('create_goal')`` has passed the
    3-gate decision, so the resulting ``WorkItemCreated`` event is paired
    with a ``CapabilityInvoked`` audit record.
    """
    from app.core.runtime.kernel_instance import kernel

    goal_id = str(uuid.uuid4())

    kernel.emit_event(
        "WorkItemCreated",
        "work_item",
        goal_id,
        payload={
            "title": title,
            "description": description or "",
            "work_type": "goal",
            "status": "active",
            "importance": importance,
            "urgency": 0.5,
        } | ({"deadline": deadline} if deadline else {}),
        actor="user",
    )

    return json.dumps({
        "goal_id": goal_id,
        "title": title,
        "status": "created",
        "message": f"已创建目标「{title}」",
    }, ensure_ascii=False)


def _writer_update_goal_progress(
    goal_id: str,
    progress: float,
    note: str = "",
) -> str:
    """Tool handler — emit WorkItemUpdated for a progress change."""
    from app.core.runtime.kernel_instance import kernel

    progress = max(0.0, min(1.0, progress))

    kernel.emit_event(
        "WorkItemUpdated",
        "work_item",
        goal_id,
        payload={"progress": progress},
        actor="user",
    )

    msg = f"目标进度已更新为 {progress * 100:.0f}%"
    if note:
        msg += f"（{note}）"

    return json.dumps({
        "goal_id": goal_id,
        "progress": progress,
        "status": "updated",
        "message": msg,
    }, ensure_ascii=False)


def _writer_complete_goal(goal_id: str, reflection: str = "") -> str:
    """Tool handler — emit WorkItemStatusChanged to complete a goal."""
    from app.core.runtime.kernel_instance import kernel

    kernel.emit_event(
        "WorkItemStatusChanged",
        "work_item",
        goal_id,
        payload={"status": "completed"},
        actor="user",
    )

    # 如果有反思，存入记忆（read-only capability path, not a goal write)
    if reflection:
        from app.core.agents.memory_engine import memory_engine
        memory_engine.store_memory(
            category="event",
            content=f"完成目标：{reflection}",
            source=f"goal:{goal_id}",
            actor="user",
        )

    return json.dumps({
        "goal_id": goal_id,
        "status": "completed",
        "message": "目标已完成！干得漂亮。" + (f" 已记录你的心得：{reflection}" if reflection else ""),
    }, ensure_ascii=False)


# ─── LLM-facing surface (goes through invoke_capability) ───────────────────


def _current_execution_id() -> str | None:
    """Read the execution_id ContextVar set by the Scheduler.

    Returns None when invoked outside a scheduler-dispatched handler (e.g. in
    tests), in which case ``invoke_capability`` skips execution ownership
    enforcement because actor='user' is not in RUNTIME_OWNERSHIP_ACTORS.
    """
    from app.core.runtime.execution import get_current_execution_id
    return get_current_execution_id()


class GoalsServer:
    """Goal management tools for AI-driven goal operations.

    These methods are async because they route through
    ``kernel.invoke_capability``. The actual emit_event side effects live in
    the ``_writer_*`` functions above, which ``mcp_hub`` registers as the tool
    handlers. This split is what makes the 3-gate authorization enforceable
    on goal writes (see ARCHITECTURE_SURVIVAL_REVIEW Critical #2).
    """

    async def create_goal(self, title: str, description: str = "",
                          importance: float = 0.5, deadline: str = "") -> str:
        """Create a new goal via the capability gate."""
        from app.core.runtime.kernel_instance import kernel

        result = await kernel.invoke_capability(
            "create_goal",
            args={
                "title": title,
                "description": description,
                "importance": importance,
                "deadline": deadline,
            },
            actor="user",
            execution_id=_current_execution_id(),
        )
        # invoke_capability returns a dict; passthrough on success, surface
        # the error string on denial/failure so the LLM sees a useful reason.
        return result.get("result") or json.dumps(
            {"error": result.get("error", "unknown")}, ensure_ascii=False,
        )

    async def update_progress(self, goal_id: str, progress: float,
                              note: str = "") -> str:
        """Update a goal's progress (0.0 to 1.0)."""
        from app.core.runtime.kernel_instance import kernel

        result = await kernel.invoke_capability(
            "update_goal_progress",
            args={"goal_id": goal_id, "progress": progress, "note": note},
            actor="user",
            execution_id=_current_execution_id(),
        )
        return result.get("result") or json.dumps(
            {"error": result.get("error", "unknown")}, ensure_ascii=False,
        )

    async def complete_goal(self, goal_id: str, reflection: str = "") -> str:
        """Mark a goal as completed, optionally with a reflection."""
        from app.core.runtime.kernel_instance import kernel

        result = await kernel.invoke_capability(
            "complete_goal",
            args={"goal_id": goal_id, "reflection": reflection},
            actor="user",
            execution_id=_current_execution_id(),
        )
        return result.get("result") or json.dumps(
            {"error": result.get("error", "unknown")}, ensure_ascii=False,
        )

    def list_active_goals(self) -> str:
        """List the user's active goals.

        Read-only path; no capability gate required (matches the existing
        auto_allow classification in capability_policy.json).

        v1.0 Phase 3b: prefer work_items(work_type='goal'), fall back to goals.
        """
        from app.core.runtime.kernel_instance import kernel

        goals = kernel.query_state(
            "work_items", work_type="goal", status="active",
            limit=20, order="importance_desc",
        )

        return json.dumps({
            "count": len(goals),
            "goals": [{"id": g["id"], "title": g["title"], "progress": g.get("progress", 0),
                        "importance": g.get("importance", 0.5)} for g in goals],
        }, ensure_ascii=False)


goals_server = GoalsServer()
