"""Morning Brief generator — creates a daily morning brief for the user."""

from datetime import UTC, datetime

from app.core.runtime.agency_gate import rank_active_goals_for_brief
from app.core.runtime.kernel_instance import kernel
from app.core.telemetry.event_recorder import Event, event_recorder
from app.product.notifications import create_notification, find_notification


def generate_morning_brief() -> dict | None:
    """Generate a morning brief with top priorities and reminders.

    Returns the brief as a dict, or None if no active goals.
    """
    now = datetime.now(UTC)

    goals = rank_active_goals_for_brief(kernel, limit=5)
    stagnant = kernel.query_state(
        "goals",
        status="active",
        last_activity_older_than_days=3,
        order="last_activity_asc",
        limit=500,
    )
    deadlines = kernel.query_state(
        "goals", status="active", deadline_within_days=3, limit=50
    )
    deadlines.sort(key=lambda d: d.get("deadline") or "")

    top_priorities = goals[:3]
    if not top_priorities and not deadlines:
        return None

    title = f"晨间简报 - {now.strftime('%Y-%m-%d %A')}"

    # Idempotent: skip if today's brief already exists
    existing = find_notification("brief", title)
    if existing:
        return existing

    content_lines = ["# ☀️ 晨间简报", f"日期: {now.strftime('%Y年%m月%d日 %A')}", ""]

    if top_priorities:
        content_lines.append("## 📌 今日 Top 3 优先目标")
        for i, g in enumerate(top_priorities, 1):
            content_lines.append(f"{i}. {g['title']}")
        content_lines.append("")

    if deadlines:
        content_lines.append("## ⏰ 临近 Deadline")
        for d in deadlines:
            delta = datetime.fromisoformat(d["deadline"]) - now
            days_left = delta.days
            label = "今天截止" if days_left == 0 else f"{days_left}天后截止"
            content_lines.append(f"- {d['title']} ({label})")
        content_lines.append("")

    if stagnant:
        content_lines.append("## ⚠️ 停滞提醒")
        for s in stagnant[:3]:
            content_lines.append(f"- {s['title']}")
        content_lines.append("")

    content = "\n".join(content_lines)

    notification = create_notification("brief", title, content)

    event_recorder.record(Event(
        type="morning_brief",
        summary=f"Morning brief generated: {len(top_priorities)} priorities",
        payload={"top_priorities": [g["title"] for g in top_priorities]},
    ))

    return {
        **notification,
        "top_priorities": [{"title": g["title"], "deadline": g.get("deadline")} for g in top_priorities],
        "deadlines": [{"title": d["title"], "deadline": d["deadline"]} for d in deadlines],
        "stagnant": [{"title": s["title"]} for s in stagnant],
    }
