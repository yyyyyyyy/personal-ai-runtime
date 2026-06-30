"""Timeline API — human-readable event log browsing."""

from fastapi import APIRouter, Query

from app.core.runtime.kernel_instance import kernel

router = APIRouter(prefix="/api/timeline", tags=["timeline"])

# Event type → human-readable label mapping
EVENT_LABELS: dict[str, str] = {
    "GoalCreated": "创建了目标",
    "GoalUpdated": "更新了目标",
    "GoalCompleted": "完成了目标",
    "GoalActionCreated": "为目标添加了任务",
    "GoalActionCompleted": "完成了任务",
    "GoalActionUpdated": "更新了任务",
    "GoalDecomposed": "AI 拆解了目标",
    "MemoryDerived": "AI 记住了新信息",
    "MemoryUpdated": "AI 更新了记忆",
    "MemoryDeleted": "移除了记忆",
    "ConversationCreated": "发起了新对话",
    "MessageAdded": "发送了消息",
    "ChatRequested": "发起了 AI 对话",
    "ChatTextDelta": "AI 正在回复",
    "ChatDone": "AI 回复完成",
    "CapabilityInvoked": "调用了工具",
    "ApprovalRequested": "请求了操作确认",
    "ApprovalResolved": "操作已完成确认",
    "InboxEmailReceived": "收到了新邮件",
    "InboxDigestGenerated": "AI 生成了邮件摘要",
    "TimerFired": "定时任务触发",
    "PatternAggregated": "AI 分析了活动模式",
    "BackgroundTaskCreated": "创建了后台任务",
    "BackgroundTaskCompleted": "后台任务完成",
    "NotificationCreated": "AI 给出了提醒",
    "WorldModelSnapshotted": "AI 记录了世界认知",
}


def _translate_event(event) -> dict:
    """Translate an Event object into a human-readable timeline item."""
    event_type = event.type
    label = EVENT_LABELS.get(event_type, f"系统事件: {event_type}")
    payload = event.payload or {}
    actor = event.actor

    # Build a descriptive sentence
    description = label
    if event_type == "GoalCreated":
        description = f'{label}「{payload.get("title", "")}」'
    elif event_type == "GoalCompleted":
        description = f'{label}「{payload.get("title", "")}」'
    elif event_type == "GoalActionCompleted":
        description = f'{label}「{payload.get("title", "")}」'
    elif event_type == "MemoryDerived":
        content = payload.get("content", "")
        snippet = content[:60] + "…" if len(content) > 60 else content
        description = f'{label}: {snippet}'
    elif event_type == "BeliefFormed":
        content = payload.get("content", "")
        snippet = content[:60] + "…" if len(content) > 60 else content
        description = f'{label}: {snippet}'
    elif event_type == "ChatRequested":
        description = label
    elif event_type == "CapabilityInvoked":
        description = f'{label}「{payload.get("capability_name", event_type)}」'
    elif event_type == "ApprovalRequested":
        description = f'{label}: {payload.get("capability_name", "")}'
    elif event_type == "InboxEmailReceived":
        description = f'{label}: {payload.get("subject", "")}'
    elif event_type == "BackgroundTaskCreated":
        description = f'{label}: {payload.get("task_title", payload.get("title", ""))}'
    elif event_type == "NotificationCreated":
        description = f'{label}: {payload.get("title", "")}'

    return {
        "id": event.id,
        "seq": event.seq,
        "type": event_type,
        "description": description,
        "actor": actor,
        "ts": event.ts,
        "payload_snippet": {
            k: str(v)[:100] for k, v in (payload or {}).items()
            if k not in ("full_text", "raw_body", "params")
        },
    }


EVENT_ICONS: dict[str, str] = {
    "GoalCreated": "target",
    "GoalUpdated": "target",
    "GoalCompleted": "check-circle",
    "GoalActionCreated": "check",
    "GoalActionCompleted": "check-circle",
    "MemoryDerived": "brain",
    "MemoryUpdated": "brain",
    "ConversationCreated": "message-square",
    "MessageAdded": "message-square",
    "ChatRequested": "message-square",
    "ChatDone": "message-square",
    "CapabilityInvoked": "zap",
    "ApprovalRequested": "shield",
    "ApprovalResolved": "shield-check",
    "InboxEmailReceived": "mail",
    "TimerFired": "clock",
    "NotificationCreated": "bell",
    "BackgroundTaskCreated": "play",
    "BackgroundTaskCompleted": "check-circle",
}


@router.get("/events")
async def list_timeline_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    event_type: str | None = Query(None, description="Filter by event type"),
    date_from: str | None = Query(None, description="ISO date string, e.g. 2026-01-01"),
    date_to: str | None = Query(None, description="ISO date string, e.g. 2026-06-30"),
):
    """Return paginated, human-readable timeline events.

    Events are ordered by seq descending (newest first).
    """
    # Build query filters
    since_ts = None
    if date_from:
        since_ts = f"{date_from}T00:00:00+00:00"
    if date_to:
        # read_events uses until_ts
        pass  # We'll filter in Python for simplicity

    events = kernel.read_events(
        since_ts=since_ts,
        limit=500,  # Fetch a large batch, we'll paginate and filter
        order="desc",
    )

    # Filter by type
    if event_type:
        events = [e for e in events if e.type == event_type]

    # Filter by date_to
    if date_to:
        end_ts = f"{date_to}T23:59:59+00:00"
        events = [e for e in events if e.ts <= end_ts]

    total = len(events)

    # Paginate
    start = (page - 1) * page_size
    page_events = events[start:start + page_size]

    # Translate to human-readable items
    items = [_translate_event(e) for e in page_events]
    if event_type:
        for item in items:
            item["icon"] = EVENT_ICONS.get(event_type, "activity")

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": start + page_size < total,
        "icons": EVENT_ICONS,
    }
