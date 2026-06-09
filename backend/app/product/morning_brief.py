"""Morning Brief generator — creates a daily morning brief for the user."""

import uuid
from datetime import datetime

from app.core.telemetry.event_recorder import Event, event_recorder
from app.store.database import db


def generate_morning_brief() -> dict | None:
    """Generate a morning brief with top priorities and reminders.

    Returns the brief as a dict, or None if no active goals.
    """
    now = datetime.utcnow()

    # Get active goals sorted by priority
    with db.get_db() as conn:
        goals = conn.execute(
            """SELECT * FROM goals WHERE status = 'active'
               ORDER BY importance * urgency DESC LIMIT 5"""
        ).fetchall()
        goals = [dict(g) for g in goals]

        # Get stagnant goals
        stagnant = conn.execute(
            """SELECT * FROM goals WHERE status = 'active'
               AND last_activity_at < datetime('now', '-3 days')"""
        ).fetchall()
        stagnant = [dict(s) for s in stagnant]

        # Get imminent deadlines (within 3 days)
        deadlines = conn.execute(
            """SELECT * FROM goals WHERE status = 'active'
               AND deadline IS NOT NULL
               AND deadline BETWEEN datetime('now') AND datetime('now', '+3 days')
               ORDER BY deadline ASC"""
        ).fetchall()
        deadlines = [dict(d) for d in deadlines]

    top_priorities = goals[:3]
    if not top_priorities and not deadlines:
        return None

    # Idempotent: skip if today's brief already exists
    with db.get_db() as conn:
        existing = conn.execute(
            "SELECT id, title, content FROM notifications WHERE type = 'brief' AND date(created_at) = date('now') LIMIT 1"
        ).fetchone()
        if existing:
            return dict(existing)

    title = f"晨间简报 - {now.strftime('%Y-%m-%d %A')}"

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

    notification_id = str(uuid.uuid4())
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO notifications (id, type, title, content, created_at) VALUES (?, 'brief', ?, ?, ?)",
            (notification_id, title, content, now.isoformat()),
        )

    event_recorder.record(Event(
        type="morning_brief",
        summary=f"Morning brief generated: {len(top_priorities)} priorities",
        payload={"top_priorities": [g["title"] for g in top_priorities]},
    ))

    return {
        "id": notification_id,
        "type": "brief",
        "title": title,
        "content": content,
        "top_priorities": [{"title": g["title"], "deadline": g.get("deadline")} for g in top_priorities],
        "deadlines": [{"title": d["title"], "deadline": d["deadline"]} for d in deadlines],
        "stagnant": [{"title": s["title"]} for s in stagnant],
    }
