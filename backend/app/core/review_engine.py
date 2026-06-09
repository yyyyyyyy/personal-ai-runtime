"""Review Engine — generates Daily, Weekly, and Monthly reviews.

Review is the key value-producing component: it analyzes events, summarizes progress,
detects problems, and suggests adjustments. Reviews complete the Goal→Action→Event→Memory→Review→Goal loop.
"""

import json
import uuid
from datetime import datetime, timedelta

from app.core.agents.memory_engine import memory_engine
from app.store.database import db


class ReviewEngine:
    """Generates periodic reviews by aggregating events and querying state."""

    def generate_daily_review(self, date: str | None = None) -> str:
        """Generate a daily review for the given date (default: today)."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        events = self._get_events_for_date(date)
        goals = self._get_active_goals()
        stagnant = self._get_stagnant_goals()

        review_id = str(uuid.uuid4())
        content = self._build_review_content("daily", date, date, events, goals, stagnant)

        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO reviews (id, type, period_start, period_end, content, key_insights, created_at) "
                "VALUES (?, 'daily', ?, ?, ?, ?, ?)",
                (review_id, date, date, content, json.dumps(self._extract_insights(content)),
                 datetime.utcnow().isoformat()),
            )

        # Store key findings as memories
        if stagnant:
            for g in stagnant[:2]:
                memory_engine.store_memory(
                    f"目标「{g['title']}」已停滞超过3天，需要重新评估或采取行动",
                    category="fact",
                    source=f"daily_review_{date}",
                )

        return review_id

    def generate_weekly_review(self) -> str:
        """Generate a weekly review for the past 7 days."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        events = self._get_events_for_period(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        goals = self._get_active_goals()
        completed = self._get_completed_goals(start_date.strftime("%Y-%m-%d"))

        review_id = str(uuid.uuid4())
        content = self._build_review_content(
            "weekly", start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"),
            events, goals, completed
        )

        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO reviews (id, type, period_start, period_end, content, key_insights, created_at) "
                "VALUES (?, 'weekly', ?, ?, ?, ?, ?)",
                (review_id, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"),
                 content, json.dumps(self._extract_insights(content)), datetime.utcnow().isoformat()),
            )

        return review_id

    def generate_monthly_review(self) -> str:
        """Generate a monthly review for the past 30 days."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        events = self._get_events_for_period(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        goals = self._get_active_goals()
        completed = self._get_completed_goals(start_date.strftime("%Y-%m-%d"))

        review_id = str(uuid.uuid4())
        content = self._build_review_content(
            "monthly", start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"),
            events, goals, completed
        )

        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO reviews (id, type, period_start, period_end, content, key_insights, created_at) "
                "VALUES (?, 'monthly', ?, ?, ?, ?, ?)",
                (review_id, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"),
                 content, json.dumps(self._extract_insights(content)), datetime.utcnow().isoformat()),
            )

        return review_id

    def _get_events_for_date(self, date: str) -> list[dict]:
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE date(timestamp) = ? ORDER BY timestamp ASC",
                (date,),
            ).fetchall()
        return [dict(r) for r in rows]

    def _get_events_for_period(self, start: str, end: str) -> list[dict]:
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE date(timestamp) BETWEEN ? AND ? ORDER BY timestamp ASC",
                (start, end),
            ).fetchall()
        return [dict(r) for r in rows]

    def _get_active_goals(self) -> list[dict]:
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM goals WHERE status = 'active' ORDER BY importance DESC, urgency DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def _get_stagnant_goals(self) -> list[dict]:
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM goals WHERE status = 'active' "
                "AND last_activity_at < datetime('now', '-3 days')"
            ).fetchall()
        return [dict(r) for r in rows]

    def _get_completed_goals(self, since: str) -> list[dict]:
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM goals WHERE status = 'completed' AND updated_at >= ?",
                (since,),
            ).fetchall()
        return [dict(r) for r in rows]

    def _build_review_content(
        self, review_type: str, start: str, end: str,
        events: list[dict], goals: list[dict], extra: list[dict]
    ) -> str:
        """Build a structured review content string (template-based, for LLM to polish)."""

        period_label = {
            "daily": f"日期: {start}",
            "weekly": f"周期: {start} ~ {end}",
            "monthly": f"周期: {start} ~ {end}",
        }.get(review_type, "")

        lines = [f"# {review_type.upper()} 复盘\n", period_label, ""]

        # Event summary
        lines.append("## 事件摘要")
        events_by_type = {}
        for e in events:
            t = e["type"]
            events_by_type.setdefault(t, 0)
            events_by_type[t] += 1

        for t, count in events_by_type.items():
            lines.append(f"- {t}: {count} 条")
        lines.append(f"\n总计: {len(events)} 条事件")
        lines.append("")

        # Goal progress
        lines.append("## 目标进展")
        if goals:
            for g in goals:
                lines.append(f"- [{g['status']}] {g['title']}")
                if g.get("deadline"):
                    lines.append(f"  截止日期: {g['deadline']}")
        else:
            lines.append("暂无活跃目标")
        lines.append("")

        # Stagnant goals (for daily review)
        if review_type == "daily" and extra:
            lines.append("## ⚠️ 停滞目标")
            for g in extra:
                days = "未知"
                if g.get("last_activity_at"):
                    delta = datetime.now() - datetime.fromisoformat(g["last_activity_at"])
                    days = f"{delta.days}天"
                lines.append(f"- {g['title']} (停滞 {days})")
            lines.append("")

        # Completed goals (for weekly/monthly)
        if review_type in ("weekly", "monthly") and extra:
            lines.append("## ✅ 已完成目标")
            for g in extra:
                lines.append(f"- {g['title']}")
            lines.append("")

        # Suggestions
        lines.append("## AI 建议")
        lines.append("(将由 LLM 根据以上数据生成个性化建议)")
        lines.append("")

        return "\n".join(lines)

    def _extract_insights(self, content: str) -> list[str]:
        """Extract key insights from review content (simplified heuristic version)."""
        insights = []
        if "停滞目标" in content:
            insights.append("存在停滞目标，需要关注")
        if "已完成目标" in content:
            insights.append("有已完成的目标")
        return insights

    def list_reviews(self, limit: int = 10) -> list[dict]:
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM reviews ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_review(self, review_id: str) -> dict | None:
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT * FROM reviews WHERE id = ?", (review_id,)
            ).fetchone()
        return dict(row) if row else None


review_engine = ReviewEngine()
